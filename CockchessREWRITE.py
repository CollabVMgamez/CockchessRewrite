import sys
import chess
import chess.svg
import chess.engine
import chess.pgn
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
#  THE BRAIN: INTERNAL PYTHON LOGIC (PeSTO)
# ==========================================
class CockchessBrain:
    # PeSTO Evaluation Tables (Midgame / Endgame)
    # This gives the internal Python engine positional understanding
    mg_pawn = [0,0,0,0,0,0,0,0, 98,134,61,95,68,126,34,-11, -6,7,26,31,65,56,25,-20, -14,13,6,21,23,12,17,-23, -27,-2,-5,12,17,6,10,-25, -26,-4,-4,-10,3,3,33,-12, -35,-1,-20,-23,-15,24,38,-22, 0,0,0,0,0,0,0,0]
    eg_pawn = [0,0,0,0,0,0,0,0, 178,173,158,134,147,132,165,187, 94,100,85,67,56,53,82,84, 32,24,13,5,-2,4,17,17, 13,9,-3,-7,-7,-8,3,-1, 4,7,-6,1,0,-5,-1,-8, 13,8,8,10,13,0,2,-7, 0,0,0,0,0,0,0,0]
    mg_knight = [-167,-89,-34,-49,61,-97,-15,-107, -73,-41,72,36,23,62,7,-17, -47,60,37,65,84,129,73,44, -9,17,19,53,37,69,18,22, -13,4,16,13,28,19,21,-8, -23,-9,12,10,19,17,25,-16, -29,-53,-12,-3,-1,18,-14,-19, -105,-21,-58,-33,-17,-28,-19,-23]
    mg_king = [-65,23,16,-15,-56,-34,2,13, 29,-1,-20,-7,-8,-4,-38,-29, -9,24,2,-16,-20,6,22,-22, -17,-20,-12,-27,-30,-25,-14,-36, -49,-1,27,-39,-46,-44,-33,-51, -14,-14,-22,-46,-44,-30,-15,-27, 1,7,-8,-64,-43,-16,9,8, -15,36,12,-54,8,-28,24,14]
    # (Simplified tables for brevity, engine uses interpolation)

    tt = {}
    nodes = 0

    def evaluate(self, board):
        if board.is_checkmate(): return -99999 if board.turn else 99999
        if board.is_stalemate(): return 0

        mg_score, eg_score, phase = 0, 0, 0

        for sq in chess.SQUARES:
            p = board.piece_at(sq)
            if not p: continue
            
            pt = p.piece_type
            idx = sq ^ 56 if p.color == chess.WHITE else sq
            
            # Material Values
            mg, eg = 0, 0
            if pt == chess.PAWN: mg=self.mg_pawn[idx]; eg=self.eg_pawn[idx]
            elif pt == chess.KNIGHT: mg=self.mg_knight[idx]; eg=320; phase+=1
            elif pt == chess.BISHOP: mg=330; eg=330; phase+=1
            elif pt == chess.ROOK: mg=500; eg=500; phase+=2
            elif pt == chess.QUEEN: mg=900; eg=900; phase+=4
            elif pt == chess.KING: mg=self.mg_king[idx]; eg=0
            
            # Add base material
            base = {1:100, 2:320, 3:330, 4:500, 5:900, 6:0}[pt]
            
            if p.color == chess.WHITE:
                mg_score += base + mg; eg_score += base + eg
            else:
                mg_score -= base + mg; eg_score -= base + eg

        phase = min(phase, 24)
        score = ((mg_score * phase) + (eg_score * (24 - phase))) / 24
        return int(score) if board.turn == chess.WHITE else int(-score)

    def score_move(self, board, move):
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            val = {1:1, 2:3, 3:3, 4:5, 5:9, 6:0}.get(victim.piece_type, 1) if victim else 1
            return 10000 + val
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
            try:
                # PVS (Principal Variation Search)
                if i == 0:
                    score = -self.negamax(board, depth - 1, -beta, -alpha, start, limit)
                else:
                    score = -self.negamax(board, depth - 1, -alpha - 1, -alpha, start, limit)
                    if alpha < score < beta:
                        score = -self.negamax(board, depth - 1, -beta, -alpha, start, limit)
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
#  ENGINE WORKER (HANDLES 3000 VS 3500)
# ==========================================
class EngineWorker(QThread):
    update = pyqtSignal(dict)
    done = pyqtSignal(object)

    def __init__(self, mode, fen, brain, sf_path, deep):
        super().__init__()
        self.mode = mode
        self.fen = fen
        self.brain = brain
        self.sf = sf_path
        self.deep = deep

    def run(self):
        board = chess.Board(self.fen)
        
        if self.mode == "INTERNAL":
            # Python Fallback Engine (Uses PeSTO)
            self.brain.nodes = 0
            self.brain.tt.clear()
            start = time.time()
            limit = 20.0 if self.deep else 2.0
            best = list(board.legal_moves)[0]
            
            for d in range(1, 100):
                if time.time() - start > limit: break
                try:
                    alpha, beta = -99999, 99999
                    moves = sorted(board.legal_moves, key=lambda m: self.brain.score_move(board, m), reverse=True)
                    curr = None
                    
                    for move in moves:
                        board.push(move)
                        try:
                            score = -self.brain.negamax(board, d-1, -beta, -alpha, start, limit)
                        except TimeoutError:
                            board.pop(); raise TimeoutError
                        board.pop()
                        
                        if score > alpha:
                            alpha = score
                            curr = move
                    
                    if curr:
                        best = curr
                        ev = f"{alpha/100:.2f}"
                        if abs(alpha) > 80000: ev = f"MATE {(90000-abs(alpha)+d)//2}"
                        self.update.emit({"depth": d, "score": alpha, "eval": ev, "nodes": self.brain.nodes, "pv": best.uci()})
                        if abs(alpha) > 80000: break
                except TimeoutError: break
            self.done.emit((best, "Cockchess (Python)"))

        elif self.mode == "STOCKFISH":
            if not self.sf:
                self.done.emit((None, "No SF Path"))
                return
            
            try:
                # Configuration for 3000+ vs 3500+ ELO
                eng = chess.engine.SimpleEngine.popen_uci(self.sf)
                
                if self.deep:
                    # 3500+ ELO Configuration
                    eng.configure({"Hash": 256, "Threads": 4})
                    target_depth = 26
                    limit_obj = chess.engine.Limit(depth=26)
                    tag = "SF (3500+ ELO)"
                else:
                    # 3000+ ELO Configuration
                    eng.configure({"Hash": 64, "Threads": 1})
                    target_depth = 18
                    limit_obj = chess.engine.Limit(depth=18)
                    tag = "SF (3000+ ELO)"

                with eng.analysis(board, limit_obj) as analysis:
                    for info in analysis:
                        # Stop if we pass target depth
                        if info.get("depth", 0) > target_depth: break
                        
                        if "score" in info:
                            sc = info["score"].relative
                            eval_s = f"MATE {sc.mate()}" if sc.is_mate() else f"{sc.score()/100:.2f}"
                            raw = 10000 if sc.is_mate() and sc.mate()>0 else (-10000 if sc.is_mate() else sc.score())
                            pv = " ".join([m.uci() for m in info.get("pv", [])[:4]])
                            
                            self.update.emit({
                                "depth": info.get("depth", 0),
                                "score": raw,
                                "eval": eval_s,
                                "nodes": info.get("nodes", 0),
                                "pv": pv
                            })
                
                res = eng.play(board, chess.engine.Limit(time=0.1)) # Confirm best move
                eng.quit()
                self.done.emit((res.move, tag))

            except Exception as e:
                self.done.emit((None, f"SF Err: {str(e)}"))

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
                self.done.emit((None, "Load SF first."))

# ==========================================
#  GUI COMPONENTS
# ==========================================
class EvalBar(QWidget):
    def __init__(self): super().__init__(); self.setFixedWidth(30); self.pct = 0.5
    def set_val(self, s): 
        if s is None: s=0
        self.pct = (max(-1000, min(1000, s)) + 1000) / 2000
        self.update()
    def paintEvent(self, e):
        p = QPainter(self)
        h = self.height()
        p.fillRect(0, 0, self.width(), h, QColor("#333"))
        wh = int(h * self.pct)
        p.fillRect(0, h - wh, self.width(), wh, QColor("#eee"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.board = chess.Board()
        self.brain = CockchessBrain()
        self.pgn = chess.pgn.Game()
        self.node = self.pgn
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
                self.lbl_sf.setText("SF: READY"); self.lbl_sf.setStyleSheet("color:#0f0")
                break

    def init_ui(self):
        self.setWindowTitle("Cockchess: Galaxy Edition (3500+)")
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
        
        pl.addWidget(QLabel("<h1>COCKCHESS GALAXY</h1>"))
        
        # Setup
        btn_sf = QPushButton("📂 Load Stockfish")
        btn_sf.clicked.connect(self.load_sf)
        pl.addWidget(btn_sf)
        self.lbl_sf = QLabel("SF: Missing")
        self.lbl_sf.setStyleSheet("color: #f55")
        pl.addWidget(self.lbl_sf)
        
        self.combo = QComboBox()
        self.combo.addItems(["Human vs Cockchess", "Human vs Stockfish", "Cockchess vs Stockfish"])
        self.combo.currentIndexChanged.connect(self.chg_mode)
        self.combo.setStyleSheet("background:#333; padding:5px;")
        pl.addWidget(self.combo)
        
        self.chk_deep = QCheckBox("🚀 Deep Mode (3500+ ELO)")
        self.chk_deep.setStyleSheet("color: #CDD26A; font-weight: bold; padding: 5px;")
        pl.addWidget(self.chk_deep)
        
        # Controls
        row = QHBoxLayout()
        self.btn_sim = QPushButton("Start Sim")
        self.btn_sim.clicked.connect(self.run_bot)
        self.btn_sim.setStyleSheet("background-color: #d32f2f")
        self.btn_sim.hide()
        
        btn_rst = QPushButton("Reset")
        btn_rst.clicked.connect(self.reset)
        row.addWidget(btn_rst); row.addWidget(self.btn_sim)
        pl.addLayout(row)

        # Tools
        t_row = QHBoxLayout()
        btn_pgn = QPushButton("PGN"); btn_pgn.clicked.connect(self.ex_pgn)
        btn_fen = QPushButton("Copy FEN"); btn_fen.clicked.connect(self.cp_fen)
        btn_imp = QPushButton("Paste FEN"); btn_imp.clicked.connect(self.ps_fen)
        t_row.addWidget(btn_pgn); t_row.addWidget(btn_fen); t_row.addWidget(btn_imp)
        pl.addLayout(t_row)
        
        btn_c = QPushButton("Ask Coach")
        btn_c.setStyleSheet("background: #0277BD")
        btn_c.clicked.connect(self.analyze)
        pl.addWidget(btn_c)

        # Stats
        pl.addSpacing(10)
        self.lbl_e = QLabel("Eval: 0.00"); self.lbl_e.setStyleSheet("font-size:20px; font-weight:bold")
        pl.addWidget(self.lbl_e)
        self.lbl_i = QLabel("Depth: 0 | Nodes: 0")
        pl.addWidget(self.lbl_i)
        self.lbl_p = QLabel("Line: ...")
        self.lbl_p.setWordWrap(True)
        self.lbl_p.setStyleSheet("color: #CDD26A; font-style: italic")
        pl.addWidget(self.lbl_p)

        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setStyleSheet("background: #000; font-size: 11px")
        pl.addWidget(self.log)

        layout.addWidget(panel)
        self.svg.mousePressEvent = self.click_board

    def load_sf(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select SF")
        if p: self.sf = p; self.lbl_sf.setText("SF: READY"); self.lbl_sf.setStyleSheet("color:#0f0")

    def chg_mode(self):
        self.mode = ["HvC", "HvS", "CvS"][self.combo.currentIndex()]
        if self.mode == "CvS": self.btn_sim.show()
        else: self.btn_sim.hide()
        self.reset()

    def reset(self):
        self.board.reset()
        self.pgn = chess.pgn.Game()
        self.node = self.pgn
        self.brain.tt.clear()
        self.log.clear()
        self.bar.set_val(0)
        self.refresh()

    def ex_pgn(self): pyperclip.copy(str(self.pgn)); self.log.append("PGN Copied")
    def cp_fen(self): pyperclip.copy(self.board.fen()); self.log.append("FEN Copied")
    def ps_fen(self):
        t, o = QInputDialog.getText(self, "Import", "Paste FEN:")
        if o and t:
            try: self.board.set_fen(t); self.refresh(); self.log.append("FEN Loaded")
            except: self.log.append("Bad FEN")

    def refresh(self):
        f = {}
        if self.selected:
            f[self.selected] = "#ffff00aa"
            for m in self.board.legal_moves:
                if m.from_square == self.selected: f[m.to_square] = "#00ff0066"
        
        arr = []
        if self.board.move_stack:
            m = self.board.peek()
            arr = [chess.svg.Arrow(m.from_square, m.to_square, color="#CDD26Aaa")]
        if self.board.is_check(): f[self.board.king(self.board.turn)] = "#ff0000cc"

        d = chess.svg.board(self.board, size=800, fill=f, arrows=arr, colors={'square light':'#e0c094', 'square dark':'#8a5d3b'})
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
                self.node = self.node.add_variation(m)
                self.selected = None; self.refresh()
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
        self.worker.update.connect(self.upd)
        self.worker.done.connect(self.done)
        self.worker.start()

    def upd(self, d):
        self.bar.set_val(d['score'])
        self.lbl_e.setText(f"Eval: {d['eval']}")
        self.lbl_i.setText(f"D: {d['depth']} | N: {d['nodes']}")
        self.lbl_p.setText(d['pv'])

    def done(self, d):
        m, t = d
        self.thinking = False
        if m:
            self.board.push(m)
            self.node = self.node.add_variation(m)
            self.refresh()
            self.log.append(f"{t}: {m.uci()}")
            if self.mode == "CvS" and not self.board.is_game_over():
                QTimer.singleShot(200, self.run_bot)
        else: self.log.append(f"Err: {t}")

    def analyze(self):
        self.worker = EngineWorker("ANALYZE", self.board.fen(), self.brain, self.sf, False)
        self.worker.done.connect(lambda d: self.log.append(d[1]))
        self.worker.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
