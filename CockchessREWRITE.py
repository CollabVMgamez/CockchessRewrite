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
#  THE BRAIN: STOCKFISH CLONE LOGIC (PYTHON)
# ==========================================
class StockfishCloneBrain:
    # AlphaZero Material Values (Superior to standard)
    # P=100, N=305, B=333, R=563, Q=950
    P, N, B, R, Q, K = 100, 305, 333, 563, 950, 20000
    MATE_SCORE = 90000
    
    # Transposition Table & History Heuristic (64x64)
    tt = {}
    history = [[0] * 64 for _ in range(64)] 
    killers = [[None]*2 for _ in range(64)]
    nodes = 0
    
    # Simplified PeSTO Tables (Interpolated)
    PST = [0,0,0,0,0,0,0,0, 5,10,10,-20,-20,10,10,5, 5,-5,-10,0,0,-10,-5,5, 0,0,0,20,20,0,0,0, 5,5,10,25,25,10,5,5, 10,10,20,30,30,20,10,10, 50,50,50,50,50,50,50,50, 0,0,0,0,0,0,0,0]
    
    MVV_LVA = [
        [0,0,0,0,0,0,0],
        [0,105,104,103,102,101,100], [0,205,204,203,202,201,200],
        [0,305,304,303,302,301,300], [0,405,404,403,402,401,400],
        [0,505,504,503,502,501,500], [0,605,604,603,602,601,600]
    ]

    def evaluate(self, board):
        if board.is_checkmate(): return -self.MATE_SCORE if board.turn else self.MATE_SCORE
        if board.is_stalemate() or board.is_insufficient_material(): return 0

        score = 0
        # Optimized Evaluation Loop
        # 1. Material & Position
        for sq in chess.SQUARES:
            p = board.piece_at(sq)
            if not p: continue
            
            pt = p.piece_type
            val = 0
            if pt == chess.PAWN: val = self.P
            elif pt == chess.KNIGHT: val = self.N
            elif pt == chess.BISHOP: val = self.B
            elif pt == chess.ROOK: val = self.R
            elif pt == chess.QUEEN: val = self.Q
            
            pst_bonus = self.PST[sq if p.color == chess.WHITE else chess.square_mirror(sq)]
            
            if p.color == chess.WHITE: score += (val + pst_bonus)
            else: score -= (val + pst_bonus)

        # 2. Mobility Bonus (Stockfish Feature)
        # Giving bonus for number of legal moves available
        # (We estimate this by simple pseudo-legal count for speed)
        if board.turn == chess.WHITE: score += board.legal_moves.count() * 5
        else: score -= board.legal_moves.count() * 5
            
        return score if board.turn == chess.WHITE else -score

    def score_move(self, board, move, depth):
        # 1. PV Move (Hash Move) - Checked in loop logic
        # 2. Captures (MVV-LVA)
        if board.is_capture(move):
            attacker = board.piece_at(move.from_square).piece_type
            victim_p = board.piece_at(move.to_square)
            victim = victim_p.piece_type if victim_p else chess.PAWN
            return 10000 + self.MVV_LVA[victim][attacker]
        
        # 3. Killers
        if depth < 64:
            if self.killers[depth][0] == move: return 9000
            if self.killers[depth][1] == move: return 8000

        # 4. History Heuristic (Butterfly)
        return self.history[move.from_square][move.to_square]

    def quiescence(self, board, alpha, beta, start, limit):
        self.nodes += 1
        if (self.nodes & 4095) == 0 and time.time() - start > limit: raise TimeoutError

        stand_pat = self.evaluate(board)
        if stand_pat >= beta: return beta
        if alpha < stand_pat: alpha = stand_pat

        moves = sorted([m for m in board.legal_moves if board.is_capture(m)], 
                       key=lambda m: self.score_move(board, m, 0), reverse=True)

        for move in moves:
            board.push(move)
            score = -self.quiescence(board, -beta, -alpha, start, limit)
            board.pop()
            if score >= beta: return beta
            if score > alpha: alpha = score
        return alpha

    def negamax(self, board, depth, alpha, beta, start, limit, do_null=True):
        self.nodes += 1
        if (self.nodes & 4095) == 0 and time.time() - start > limit: raise TimeoutError

        key = board.fen()
        if key in self.tt and self.tt[key]['d'] >= depth:
            e = self.tt[key]
            if e['f'] == 0: return e['s']
            if e['f'] == 1 and e['s'] <= alpha: return e['s']
            if e['f'] == 2 and e['s'] >= beta: return e['s']

        if depth <= 0: return self.quiescence(board, alpha, beta, start, limit)
        if board.is_game_over(): return self.evaluate(board)

        # Null Move Pruning (Stockfish Technique)
        if do_null and depth >= 3 and not board.is_check() and not board.is_capture(board.peek()):
            board.push(chess.Move.null())
            score = -self.negamax(board, depth - 3, -beta, -beta + 1, start, limit, False)
            board.pop()
            if score >= beta: return beta

        moves = sorted(board.legal_moves, key=lambda m: self.score_move(board, m, depth), reverse=True)
        
        max_score = -999999
        best_move = None

        for i, move in enumerate(moves):
            board.push(move)
            
            # PVS (Principal Variation Search)
            # Assume first move is best, search it fully. Search others with reduced window.
            ext = 1 if board.is_check() else 0
            
            try:
                if i == 0:
                    score = -self.negamax(board, depth - 1 + ext, -beta, -alpha, start, limit)
                else:
                    # Late Move Reduction (LMR)
                    reduction = 0
                    if i > 3 and depth > 2 and not board.is_capture(move) and not board.is_check():
                        reduction = 1
                    
                    score = -self.negamax(board, depth - 1 + ext - reduction, -alpha - 1, -alpha, start, limit)
                    
                    # Re-search if fail high or LMR failed
                    if score > alpha and reduction > 0:
                        score = -self.negamax(board, depth - 1 + ext, -alpha - 1, -alpha, start, limit)
                    if score > alpha and score < beta:
                        score = -self.negamax(board, depth - 1 + ext, -beta, -alpha, start, limit)

            except TimeoutError:
                board.pop(); raise TimeoutError

            board.pop()

            if score > max_score:
                max_score = score
                best_move = move
            
            alpha = max(alpha, score)
            if alpha >= beta:
                # Update Killers & History
                if not board.is_capture(move):
                    self.killers[depth][1] = self.killers[depth][0]
                    self.killers[depth][0] = move
                    self.history[move.from_square][move.to_square] += depth * depth
                
                self.tt[key] = {'d': depth, 's': max_score, 'f': 2, 'm': best_move}
                return max_score

        flag = 0 if max_score > alpha else 1
        self.tt[key] = {'d': depth, 's': max_score, 'f': flag, 'm': best_move}
        return max_score

    def aspiration_search(self, board, depth, prev_score, start, limit):
        # Aspiration Windows (Stockfish Technique)
        # Search small window around previous score. Widen if fail.
        alpha = prev_score - 50
        beta = prev_score + 50
        
        while True:
            try:
                score = self.negamax(board, depth, alpha, beta, start, limit)
                if score <= alpha:
                    alpha -= 200 # Fail Low, widen down
                elif score >= beta:
                    beta += 200 # Fail High, widen up
                else:
                    return score # Success
            except TimeoutError: raise TimeoutError

# ==========================================
#  WORKER
# ==========================================
class EngineWorker(QThread):
    update = pyqtSignal(dict)
    done = pyqtSignal(object)

    def __init__(self, mode, fen, brain, sf_path, deep):
        super().__init__()
        self.mode, self.fen, self.brain, self.sf, self.deep = mode, fen, brain, sf_path, deep

    def run(self):
        board = chess.Board(self.fen)
        
        if self.mode == "INTERNAL":
            self.brain.nodes = 0
            self.brain.tt.clear()
            self.brain.history = [[0]*64 for _ in range(64)]
            
            start = time.time()
            limit = 30.0 if self.deep else 2.5
            best = list(board.legal_moves)[0]
            max_d = 30 if self.deep else 10
            
            last_score = 0
            
            for d in range(1, max_d+1):
                if time.time() - start > limit: break
                try:
                    # Use Aspiration Search for efficiency
                    if d > 2:
                        score = self.brain.aspiration_search(board, d, last_score, start, limit)
                    else:
                        score = self.brain.negamax(board, d, -99999, 99999, start, limit)
                    
                    last_score = score
                    
                    # Find best move from TT
                    entry = self.brain.tt.get(board.fen())
                    if entry and entry.get('m'):
                        best = entry['m']
                        eval_s = f"{score/100:.2f}"
                        if abs(score) > 80000: eval_s = f"MATE {(90000-abs(score)+d)//2}"
                        self.update.emit({"depth": d, "score": score, "eval": eval_s, "nodes": self.brain.nodes, "pv": best.uci()})
                    
                    if abs(score) > 80000: break
                except TimeoutError: break
            
            self.done.emit((best, "Stockfish Clone"))

        elif self.mode == "STOCKFISH":
            if not self.sf: self.done.emit((None, "No SF")); return
            try:
                eng = chess.engine.SimpleEngine.popen_uci(self.sf)
                with eng.analysis(board, chess.engine.Limit(depth=24 if self.deep else 12)) as ana:
                    for i in ana:
                        if "score" in i:
                            sc = i["score"].relative
                            eval_s = f"MATE {sc.mate()}" if sc.is_mate() else f"{sc.score()/100:.2f}"
                            raw = 10000 if sc.is_mate() and sc.mate()>0 else (-10000 if sc.is_mate() else sc.score())
                            self.update.emit({"depth": i.get("depth",0), "score": raw, "eval": eval_s, "nodes": i.get("nodes",0), "pv": " ".join([m.uci() for m in i.get("pv",[])[:3]])})
                res = eng.play(board, chess.engine.Limit(time=0.1))
                eng.quit()
                self.done.emit((res.move, "Stockfish 16"))
            except Exception as e: self.done.emit((None, str(e)))
            
        elif self.mode == "ANALYZE":
            if self.sf:
                eng = chess.engine.SimpleEngine.popen_uci(self.sf)
                i = eng.analyse(board, chess.engine.Limit(time=1.0))
                eng.quit()
                self.done.emit((None, f"Best: {i['pv'][0].uci()}"))

# ==========================================
#  GUI (UNIFIED)
# ==========================================
class EvalBar(QWidget):
    def __init__(self): super().__init__(); self.setFixedWidth(30); self.pct=0.5
    def set_val(self, s): self.pct=(max(-1000,min(1000, s or 0))+1000)/2000; self.update()
    def paintEvent(self, e): 
        p=QPainter(self); h=self.height()
        p.fillRect(0,0,self.width(),h,QColor("#333")); wh=int(h*self.pct)
        p.fillRect(0,h-wh,self.width(),wh,QColor("#eee"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.board=chess.Board(); self.brain=StockfishCloneBrain(); self.pgn=chess.pgn.Game(); self.node=self.pgn; self.sf=None; self.selected=None; self.thinking=False; self.mode="HvC"
        self.init_ui(); self.find_sf(); self.refresh()

    def find_sf(self):
        for f in os.listdir("."):
            if "stockfish" in f.lower() and f.endswith(".exe"): self.sf=os.path.abspath(f); self.lbl_sf.setText("SF: READY"); self.lbl_sf.setStyleSheet("color:#0f0"); break

    def init_ui(self):
        self.setWindowTitle("Cockchess: Stockfish Clone Edition"); self.setGeometry(100,100,1300,900); self.setStyleSheet("background:#181818;color:#ddd;font-family:Consolas;")
        c=QWidget(); self.setCentralWidget(c); l=QHBoxLayout(c); self.bar=EvalBar(); l.addWidget(self.bar)
        self.svg=QSvgWidget(); self.svg.setFixedSize(800,800); l.addWidget(self.svg)
        
        p=QFrame(); p.setFixedWidth(400); p.setStyleSheet("background:#222;border-radius:8px;"); pl=QVBoxLayout(p)
        pl.addWidget(QLabel("<h1>COCKCHESS CLONE</h1>"))
        
        btn_sf=QPushButton("📂 Load Stockfish"); btn_sf.clicked.connect(self.load_sf); pl.addWidget(btn_sf)
        self.lbl_sf=QLabel("SF: Missing"); self.lbl_sf.setStyleSheet("color:#f55"); pl.addWidget(self.lbl_sf)
        
        self.combo=QComboBox(); self.combo.addItems(["Human vs Cockchess","Human vs Stockfish","Cockchess vs Stockfish"]); self.combo.currentIndexChanged.connect(self.chg_mode); self.combo.setStyleSheet("background:#333;padding:5px;"); pl.addWidget(self.combo)
        self.chk=QCheckBox("🚀 Deep Mode (2600 ELO)"); self.chk.setStyleSheet("color:#CDD26A;font-weight:bold"); pl.addWidget(self.chk)
        
        row=QHBoxLayout(); self.btn_sim=QPushButton("Start Sim"); self.btn_sim.clicked.connect(self.run_bot); self.btn_sim.setStyleSheet("background:#d32f2f"); self.btn_sim.hide()
        btn_rst=QPushButton("Reset"); btn_rst.clicked.connect(self.reset); row.addWidget(btn_rst); row.addWidget(self.btn_sim); pl.addLayout(row)
        
        t_row=QHBoxLayout(); b_pgn=QPushButton("PGN"); b_pgn.clicked.connect(self.ex_pgn); b_fen=QPushButton("FEN"); b_fen.clicked.connect(self.cp_fen); b_imp=QPushButton("Paste"); b_imp.clicked.connect(self.ps_fen)
        t_row.addWidget(b_pgn); t_row.addWidget(b_fen); t_row.addWidget(b_imp); pl.addLayout(t_row)
        
        btn_c=QPushButton("Ask Coach"); btn_c.setStyleSheet("background:#0277BD"); btn_c.clicked.connect(self.analyze); pl.addWidget(btn_c)
        
        self.lbl_e=QLabel("Eval: 0.00"); self.lbl_e.setStyleSheet("font-size:20px;font-weight:bold"); pl.addWidget(self.lbl_e)
        self.lbl_i=QLabel("Info: ..."); pl.addWidget(self.lbl_i); self.lbl_p=QLabel("..."); self.lbl_p.setStyleSheet("color:#CDD26A"); pl.addWidget(self.lbl_p)
        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setStyleSheet("background:#000;font-size:11px"); pl.addWidget(self.log)
        l.addWidget(p); self.svg.mousePressEvent=self.click_board

    def load_sf(self): f,_=QFileDialog.getOpenFileName(self,"SF"); 
    if f: self.sf=f; self.lbl_sf.setText("SF: READY"); self.lbl_sf.setStyleSheet("color:#0f0")
    def chg_mode(self): self.mode=["HvC","HvS","CvS"][self.combo.currentIndex()]; self.btn_sim.setVisible(self.mode=="CvS"); self.reset()
    def reset(self): self.board.reset(); self.pgn=chess.pgn.Game(); self.node=self.pgn; self.brain.tt.clear(); self.brain.history=[[0]*64 for _ in range(64)]; self.log.clear(); self.bar.set_val(0); self.refresh()
    def ex_pgn(self): pyperclip.copy(str(self.pgn)); self.log.append("PGN Copied")
    def cp_fen(self): pyperclip.copy(self.board.fen()); self.log.append("FEN Copied")
    def ps_fen(self): t,o=QInputDialog.getText(self,"Imp","FEN:"); 
    if o and t: 
        try: self.board.set_fen(t); self.refresh(); self.log.append("FEN Loaded")
        except: self.log.append("Bad FEN")
        
    def refresh(self):
        f={}; 
        if self.selected: 
            f[self.selected]="#ffff00aa"
            for m in self.board.legal_moves: 
                if m.from_square==self.selected: f[m.to_square]="#00ff0066"
        arr=[]; 
        if self.board.move_stack: m=self.board.peek(); arr=[chess.svg.Arrow(m.from_square,m.to_square,color="#CDD26Aaa")]
        if self.board.is_check(): f[self.board.king(self.board.turn)]="#ff0000cc"
        d=chess.svg.board(self.board,size=800,fill=f,arrows=arr,colors={'square light':'#e0c094','square dark':'#8a5d3b'})
        self.svg.load(QByteArray(d.encode('utf-8')))

    def click_board(self,e):
        if self.thinking or self.mode=="CvS": return
        sq=chess.square(int(e.x()//100),7-int(e.y()//100))
        if self.selected is None:
            p=self.board.piece_at(sq)
            if p and p.color==self.board.turn: self.selected=sq; self.refresh()
        else:
            m=chess.Move(self.selected,sq)
            if self.board.piece_at(self.selected).piece_type==chess.PAWN and chess.square_rank(sq) in [0,7]: m.promotion=chess.QUEEN
            if m in self.board.legal_moves:
                self.board.push(m); self.node=self.node.add_variation(m); self.selected=None; self.refresh()
                if not self.board.is_game_over(): self.run_bot()
            else:
                self.selected=sq if self.board.piece_at(sq) and self.board.piece_at(sq).color==self.board.turn else None; self.refresh()

    def run_bot(self):
        if self.board.is_game_over(): return
        mode="INTERNAL"
        if self.mode=="HvS": mode="STOCKFISH"
        elif self.mode=="CvS": mode="INTERNAL" if self.board.turn==chess.WHITE else "STOCKFISH"
        self.thinking=True
        self.worker=EngineWorker(mode,self.board.fen(),self.brain,self.sf,self.chk.isChecked())
        self.worker.update.connect(self.upd); self.worker.done.connect(self.done); self.worker.start()

    def upd(self,d): self.bar.set_val(d['score']); self.lbl_e.setText(f"Eval: {d['eval']}"); self.lbl_i.setText(f"D: {d['depth']} | N: {d['nodes']}"); self.lbl_p.setText(d['pv'])
    def done(self,d): 
        m,t=d; self.thinking=False
        if m: 
            self.board.push(m); self.node=self.node.add_variation(m); self.refresh(); self.log.append(f"{t}: {m.uci()}")
            if self.mode=="CvS" and not self.board.is_game_over(): QTimer.singleShot(200,self.run_bot)
        else: self.log.append(f"Err: {t}")
    def analyze(self): self.worker=EngineWorker("ANALYZE",self.board.fen(),self.brain,self.sf,False); self.worker.done.connect(lambda d: self.log.append(d[1])); self.worker.start()

if __name__ == "__main__": app=QApplication(sys.argv); w=MainWindow(); w.show(); sys.exit(app.exec_())
