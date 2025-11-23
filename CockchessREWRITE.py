import sys
import chess
import chess.svg
import chess.engine
import chess.pgn
import chess.polyglot
import time
import os
import pyperclip
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QComboBox, QMessageBox, QFrame, QTextEdit, 
                             QCheckBox, QInputDialog)
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtCore import pyqtSlot, QThread, pyqtSignal, Qt, QByteArray, QTimer
from PyQt5.QtGui import QPainter, QColor

# ==========================================
#  THE BRAIN: INTERNAL PYTHON ENGINE
# ==========================================
class CockchessBrain:
    # Evaluation Constants
    P, N, B, R, Q, K = 100, 320, 330, 500, 900, 20000
    MATE_SCORE = 90000
    
    # Transposition Table
    tt = {}
    nodes = 0
    
    # Simplified PeSTO Tables (Midgame/Endgame interpolated)
    PST = [
        0,0,0,0,0,0,0,0, 5,10,10,-20,-20,10,10,5, 5,-5,-10,0,0,-10,-5,5, 0,0,0,20,20,0,0,0, 5,5,10,25,25,10,5,5, 10,10,20,30,30,20,10,10, 50,50,50,50,50,50,50,50, 0,0,0,0,0,0,0,0
    ]
    
    # Move Ordering (Victim - Attacker)
    MVV_LVA = [
        [0,0,0,0,0,0,0],
        [0,105,104,103,102,101,100], # P
        [0,205,204,203,202,201,200], # N
        [0,305,304,303,302,301,300], # B
        [0,405,404,403,402,401,400], # R
        [0,505,504,503,502,501,500], # Q
        [0,605,604,603,602,601,600]  # K
    ]

    def evaluate(self, board):
        if board.is_checkmate(): return -self.MATE_SCORE if board.turn else self.MATE_SCORE
        if board.is_stalemate() or board.is_insufficient_material(): return 0

        score = 0
        for sq in chess.SQUARES:
            p = board.piece_at(sq)
            if not p: continue
            
            # Material
            if p.piece_type == chess.PAWN: val = self.P
            elif p.piece_type == chess.KNIGHT: val = self.N
            elif p.piece_type == chess.BISHOP: val = self.B
            elif p.piece_type == chess.ROOK: val = self.R
            elif p.piece_type == chess.QUEEN: val = self.Q
            elif p.piece_type == chess.KING: val = self.K
            
            # Positional
            pst = self.PST[sq if p.color == chess.WHITE else chess.square_mirror(sq)]
            
            # Center Control Bonus
            bonus = 0
            if p.piece_type in [chess.PAWN, chess.KNIGHT] and sq in [27,28,35,36]: bonus = 15

            total = val + pst + bonus
            if p.color == chess.WHITE: score += total
            else: score -= total
            
        return score if board.turn == chess.WHITE else -score

    def score_move(self, board, move):
        # Captures
        if board.is_capture(move):
            attacker = board.piece_at(move.from_square).piece_type
            victim_p = board.piece_at(move.to_square)
            victim = victim_p.piece_type if victim_p else chess.PAWN
            return 10000 + self.MVV_LVA[victim][attacker]
        # Checks
        if board.gives_check(move): return 5000
        return 0

    def quiescence(self, board, alpha, beta, start, limit):
        self.nodes += 1
        if (self.nodes & 2047) == 0 and time.time() - start > limit: raise TimeoutError

        stand_pat = self.evaluate(board)
        if stand_pat >= beta: return beta
        if alpha < stand_pat: alpha = stand_pat

        moves = sorted([m for m in board.legal_moves if board.is_capture(m)], 
                       key=lambda m: self.score_move(board, m), reverse=True)

        for move in moves:
            board.push(move)
            score = -self.quiescence(board, -beta, -alpha, start, limit)
            board.pop()
            if score >= beta: return beta
            if score > alpha: alpha = score
        return alpha

    def negamax(self, board, depth, alpha, beta, start, limit):
        self.nodes += 1
        if (self.nodes & 2047) == 0 and time.time() - start > limit: raise TimeoutError

        key = board.fen()
        if key in self.tt and self.tt[key]['d'] >= depth:
            e = self.tt[key]
            if e['f'] == 0: return e['s']
            if e['f'] == 1 and e['s'] <= alpha: return e['s']
            if e['f'] == 2 and e['s'] >= beta: return e['s']

        if depth <= 0: return self.quiescence(board, alpha, beta, start, limit)
        if board.is_game_over(): return self.evaluate(board)

        moves = sorted(board.legal_moves, key=lambda m: self.score_move(board, m), reverse=True)
        max_score = -999999
        best_move = None

        for i, move in enumerate(moves):
            board.push(move)
            ext = 1 if board.is_check() else 0 # Check Extension
            
            try:
                # PVS Optimization
                if i == 0:
                    score = -self.negamax(board, depth - 1 + ext, -beta, -alpha, start, limit)
                else:
                    score = -self.negamax(board, depth - 1 + ext, -alpha - 1, -alpha, start, limit)
                    if alpha < score < beta:
                        score = -self.negamax(board, depth - 1 + ext, -beta, -alpha, start, limit)
            except TimeoutError:
                board.pop(); raise TimeoutError

            board.pop()

            if score > max_score:
                max_score = score
                best_move = move
            
            alpha = max(alpha, score)
            if alpha >= beta:
                self.tt[key] = {'d': depth, 's': max_score, 'f': 2, 'm': best_move}
                return max_score

        flag = 0 if max_score > alpha else 1
        self.tt[key] = {'d': depth, 's': max_score, 'f': flag, 'm': best_move}
        return max_score

# ==========================================
#  WORKER THREAD
# ==========================================
class EngineWorker(QThread):
    update = pyqtSignal(dict)
    done = pyqtSignal(object)

    def __init__(self, mode, fen, brain, sf_path, deep):
        super().__init__()
        self.mode = mode # "INTERNAL", "STOCKFISH", "ANALYZE"
        self.fen = fen
        self.brain = brain
        self.sf = sf_path
        self.deep = deep

    def run(self):
        board = chess.Board(self.fen)
        
        if self.mode == "INTERNAL":
            self.brain.nodes = 0
            self.brain.tt.clear()
            start = time.time()
            limit = 30.0 if self.deep else 2.0
            
            best = list(board.legal_moves)[0]
            max_d = 30 if self.deep else 8
            
            for d in range(1, max_d+1):
                if time.time() - start > limit: break
                try:
                    alpha, beta = -99999, 99999
                    moves = sorted(board.legal_moves, key=lambda m: self.brain.score_move(board, m), reverse=True)
                    curr_best = None
                    
                    for move in moves:
                        board.push(move)
                        try:
                            score = -self.brain.negamax(board, d-1, -beta, -alpha, start, limit)
                        except TimeoutError:
                            board.pop(); raise TimeoutError
                        board.pop()
                        
                        if score > alpha:
                            alpha = score
                            curr_best = move
                    
                    if curr_best:
                        best = curr_best
                        
                        # Format Score
                        eval_s = f"{alpha/100:.2f}"
                        if abs(alpha) > 80000: eval_s = f"MATE {(90000-abs(alpha)+d)//2}"
                        
                        self.update.emit({"depth": d, "score": alpha, "eval": eval_s, "nodes": self.brain.nodes, "pv": best.uci()})
                        
                        if abs(alpha) > 80000: break # Mate found

                except TimeoutError: break
            
            self.done.emit((best, "Cockchess"))

        elif self.mode == "STOCKFISH":
            if not self.sf: 
                self.done.emit((None, "No SF Path"))
                return
            
            eng = chess.engine.SimpleEngine.popen_uci(self.sf)
            
            # Analysis Stream for GUI updates
            with eng.analysis(board, chess.engine.Limit(depth=22 if self.deep else 10)) as analysis:
                for info in analysis:
                    if info.get("depth", 0) > (22 if self.deep else 10): break
                    
                    sc = info["score"].relative
                    eval_s = f"MATE {sc.mate()}" if sc.is_mate() else f"{sc.score()/100:.2f}"
                    score_raw = 10000 if sc.is_mate() and sc.mate() > 0 else (-10000 if sc.is_mate() else sc.score())
                    pv = " ".join([m.uci() for m in info.get("pv", [])[:3]])
                    
                    self.update.emit({"depth": info["depth"], "score": score_raw, "eval": eval_s, "nodes": info.get("nodes", 0), "pv": pv})
            
            # Play move
            res = eng.play(board, chess.engine.Limit(time=0.1))
            eng.quit()
            self.done.emit((res.move, "Stockfish"))

        elif self.mode == "ANALYZE":
            if self.sf:
                eng = chess.engine.SimpleEngine.popen_uci(self.sf)
                info = eng.analyse(board, chess.engine.Limit(time=1.0))
                sc = info["score"].relative
                eval_s = f"MATE {sc.mate()}" if sc.is_mate() else f"{sc.score()/100:.2f}"
                pv = info["pv"][0].uci()
                eng.quit()
                self.done.emit((None, f"Best: {pv} | Eval: {eval_s}"))
            else:
                self.done.emit((None, "Load Stockfish for Analysis."))

# ==========================================
#  WIDGET: EVAL BAR
# ==========================================
class EvalBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(30)
        self.pct = 0.5

    def set_val(self, score):
        # Clamp -1000 to 1000
        v = max(-1000, min(1000, score))
        self.pct = (v + 1000) / 2000
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        h = self.height()
        p.fillRect(0, 0, self.width(), h, QColor("#333"))
        wh = int(h * self.pct)
        p.fillRect(0, h - wh, self.width(), wh, QColor("#eee"))

# ==========================================
#  GUI
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.board = chess.Board()
        self.brain = CockchessBrain()
        self.pgn = chess.pgn.Game()
        self.pgn_node = self.pgn
        self.sf = None
        self.selected = None
        self.thinking = False
        self.mode = "HvC"
        
        self.init_ui()
        self.find_sf()
        self.refresh()

    def find_sf(self):
        for f in os.listdir("."):
            if "stockfish" in f.lower() and f.endswith(".exe"):
                self.sf = os.path.abspath(f)
                self.lbl_sf.setText("SF: LINKED")
                self.lbl_sf.setStyleSheet("color: #0f0")
                break

    def init_ui(self):
        self.setWindowTitle("Cockchess: Unified Edition")
        self.setGeometry(100, 100, 1300, 900)
        self.setStyleSheet("background-color: #181818; color: #ddd; font-family: Consolas;")

        c = QWidget(); self.setCentralWidget(c); layout = QHBoxLayout(c)

        self.bar = EvalBar()
        layout.addWidget(self.bar)

        self.svg = QSvgWidget()
        self.svg.setFixedSize(800, 800)
        layout.addWidget(self.svg)

        panel = QFrame()
        panel.setFixedWidth(400)
        panel.setStyleSheet("background-color: #222; border-radius: 8px;")
        pl = QVBoxLayout(panel)
        
        pl.addWidget(QLabel("<h1>COCKCHESS UNIFIED</h1>"))
        
        # -- SETUP --
        btn_sf = QPushButton("📂 Load Stockfish")
        btn_sf.clicked.connect(self.load_sf)
        pl.addWidget(btn_sf)
        self.lbl_sf = QLabel("SF: Missing")
        self.lbl_sf.setStyleSheet("color: #f55")
        pl.addWidget(self.lbl_sf)
        
        self.combo = QComboBox()
        self.combo.addItems(["Human vs Cockchess", "Human vs Stockfish", "Cockchess vs Stockfish"])
        self.combo.currentIndexChanged.connect(self.chg_mode)
        self.combo.setStyleSheet("background-color:#333; padding:5px;")
        pl.addWidget(self.combo)
        
        self.chk_deep = QCheckBox("🚀 Deep Thinking Mode")
        self.chk_deep.setStyleSheet("color: #CDD26A; font-weight: bold;")
        pl.addWidget(self.chk_deep)
        
        # -- CONTROLS --
        row = QHBoxLayout()
        self.btn_sim = QPushButton("Start Sim")
        self.btn_sim.clicked.connect(self.run_bot)
        self.btn_sim.setStyleSheet("background-color: #d32f2f")
        self.btn_sim.hide()
        
        btn_rst = QPushButton("Reset")
        btn_rst.clicked.connect(self.reset)
        
        row.addWidget(btn_rst)
        row.addWidget(self.btn_sim)
        pl.addLayout(row)

        # -- TOOLS --
        t_row = QHBoxLayout()
        btn_pgn = QPushButton("Export PGN")
        btn_pgn.clicked.connect(self.export_pgn)
        btn_fen = QPushButton("Copy FEN")
        btn_fen.clicked.connect(self.copy_fen)
        btn_imp = QPushButton("Paste FEN")
        btn_imp.clicked.connect(self.paste_fen)
        t_row.addWidget(btn_pgn); t_row.addWidget(btn_fen); t_row.addWidget(btn_imp)
        pl.addLayout(t_row)

        btn_coach = QPushButton("💡 Ask Coach")
        btn_coach.setStyleSheet("background-color: #0277BD")
        btn_coach.clicked.connect(self.analyze)
        pl.addWidget(btn_coach)

        # -- STATS --
        pl.addSpacing(10)
        self.lbl_eval = QLabel("Eval: 0.00"); self.lbl_eval.setStyleSheet("font-size: 20px; font-weight:bold")
        pl.addWidget(self.lbl_eval)
        self.lbl_info = QLabel("Depth: 0 | Nodes: 0")
        pl.addWidget(self.lbl_info)
        self.lbl_pv = QLabel("Line: ...")
        self.lbl_pv.setWordWrap(True)
        self.lbl_pv.setStyleSheet("color: #CDD26A; font-style: italic")
        pl.addWidget(self.lbl_pv)

        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setStyleSheet("background-color: #000; font-size: 11px")
        pl.addWidget(self.log)

        layout.addWidget(panel)
        self.svg.mousePressEvent = self.click_board

    def load_sf(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select SF")
        if p: self.sf = p; self.lbl_sf.setText("SF: LINKED"); self.lbl_sf.setStyleSheet("color: #0f0")

    def chg_mode(self):
        self.mode = ["HvC", "HvS", "CvS"][self.combo.currentIndex()]
        if self.mode == "CvS": self.btn_sim.show()
        else: self.btn_sim.hide()
        self.reset()

    def reset(self):
        self.board.reset()
        self.pgn = chess.pgn.Game()
        self.pgn_node = self.pgn
        self.brain.tt.clear()
        self.log.clear()
        self.bar.set_val(0)
        self.refresh()

    def export_pgn(self):
        pyperclip.copy(str(self.pgn))
        self.log.append("PGN Copied!")

    def copy_fen(self):
        pyperclip.copy(self.board.fen())
        self.log.append("FEN Copied!")

    def paste_fen(self):
        text, ok = QInputDialog.getText(self, "Import", "Paste FEN:")
        if ok and text:
            try:
                self.board.set_fen(text)
                self.refresh()
                self.log.append("FEN Loaded.")
            except:
                self.log.append("Invalid FEN.")

    def refresh(self):
        fill = {}
        if self.selected:
            fill[self.selected] = "#ffff00aa"
            for m in self.board.legal_moves:
                if m.from_square == self.selected: fill[m.to_square] = "#00ff0066"
        
        arr = []
        if self.board.move_stack:
            m = self.board.peek()
            arr = [chess.svg.Arrow(m.from_square, m.to_square, color="#CDD26Aaa")]
        if self.board.is_check(): fill[self.board.king(self.board.turn)] = "#ff0000cc"

        d = chess.svg.board(self.board, size=800, fill=fill, arrows=arr, colors={'square light':'#e0c094', 'square dark':'#8a5d3b'})
        self.svg.load(QByteArray(d.encode('utf-8')))

    def click_board(self, e):
        if self.thinking or self.mode == "CvS": return
        sq = chess.square(int(e.x()//100), 7-int(e.y()//100))
        if self.selected is None:
            p = self.board.piece_at(sq)
            if p and p.color == self.board.turn: self.selected = sq; self.refresh()
        else:
            m = chess.Move(self.selected, sq)
            if self.board.piece_at(self.selected).piece_type == chess.PAWN and chess.square_rank(sq) in [0,7]: m.promotion=chess.QUEEN
            if m in self.board.legal_moves:
                self.board.push(m)
                self.pgn_node = self.pgn_node.add_variation(m)
                self.selected=None; self.refresh()
                if not self.board.is_game_over(): self.run_bot()
            else:
                p = self.board.piece_at(sq)
                self.selected = sq if p and p.color == self.board.turn else None
                self.refresh()

    def run_bot(self):
        if self.board.is_game_over(): return
        mode = "INTERNAL"
        if self.mode == "HvS": mode = "STOCKFISH"
        elif self.mode == "CvS": mode = "INTERNAL" if self.board.turn == chess.WHITE else "STOCKFISH"

        self.thinking = True
        self.worker = EngineWorker(mode, self.board.fen(), self.brain, self.sf, self.chk_deep.isChecked())
        self.worker.update.connect(self.update_stats)
        self.worker.done.connect(self.bot_done)
        self.worker.start()

    def update_stats(self, d):
        self.bar.set_val(d['score'])
        self.lbl_eval.setText(f"Eval: {d['eval']}")
        self.lbl_info.setText(f"D: {d['depth']} | N: {d['nodes']}")
        self.lbl_pv.setText(d['pv'])

    def bot_done(self, data):
        move, tag = data
        self.thinking = False
        if move:
            self.board.push(move)
            self.pgn_node = self.pgn_node.add_variation(move)
            self.refresh()
            self.log.append(f"{tag}: {move.uci()}")
            if self.mode == "CvS" and not self.board.is_game_over():
                QTimer.singleShot(200, self.run_bot)
        else: self.log.append(f"Error: {tag}")

    def analyze(self):
        self.worker = EngineWorker("ANALYZE", self.board.fen(), self.brain, self.sf, False)
        self.worker.done.connect(lambda d: self.log.append(d[1]))
        self.worker.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
