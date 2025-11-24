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
#  THE BRAIN: VANGUARD LOGIC (STRATEGIC PYTHON ENGINE)
# ==========================================
class CockchessBrain:
    # PeSTO Tables (The foundation)
    mg_pawn = [0,0,0,0,0,0,0,0, 98,134,61,95,68,126,34,-11, -6,7,26,31,65,56,25,-20, -14,13,6,21,23,12,17,-23, -27,-2,-5,12,17,6,10,-25, -26,-4,-4,-10,3,3,33,-12, -35,-1,-20,-23,-15,24,38,-22, 0,0,0,0,0,0,0,0]
    eg_pawn = [0,0,0,0,0,0,0,0, 178,173,158,134,147,132,165,187, 94,100,85,67,56,53,82,84, 32,24,13,5,-2,4,17,17, 13,9,-3,-7,-7,-8,3,-1, 4,7,-6,1,0,-5,-1,-8, 13,8,8,10,13,0,2,-7, 0,0,0,0,0,0,0,0]
    mg_knight = [-167,-89,-34,-49,61,-97,-15,-107, -73,-41,72,36,23,62,7,-17, -47,60,37,65,84,129,73,44, -9,17,19,53,37,69,18,22, -13,4,16,13,28,19,21,-8, -23,-9,12,10,19,17,25,-16, -29,-53,-12,-3,-1,18,-14,-19, -105,-21,-58,-33,-17,-28,-19,-23]
    eg_knight = [-58,-38,-13,-28,-31,-27,-63,-99, -25,-8,-25,-2,-9,-25,-24,-52, -24,-20,10,9,-1,-9,-19,-41, -17,3,22,22,22,11,8,-18, -18,-6,16,25,16,17,4,-18, -23,-3,-1,15,10,-3,-20,-22, -42,-20,-10,-5,-2,-20,-23,-44, -29,-51,-23,-15,-22,-18,-50,-64]
    mg_bishop = [-29,4,-82,-37,-25,-42,7,-8, -26,16,-18,-13,30,59,18,-47, -16,37,43,40,35,50,37,-2, -4,5,19,50,37,37,7,-2, -6,13,13,26,34,12,10,4, 0,15,15,15,14,27,18,10, 4,15,16,9,23,29,24,9, -20,-21,-46,-14,-9,-21,6,8]
    eg_bishop = [-14,-21,-11,-8,-7,-9,-17,-24, -8,-4,7,-12,-3,-13,-4,-14, -4,-2,5,11,10,4,-5,-6, -10,2,2,15,11,6,6,-9, -3,-1,2,1,3,1,-2,-3, -4,-5,-5,2,-1,-3,-5,-7, -13,-5,-5,-6,-7,-4,-7,-13, -23,-10,-11,-8,-6,-11,-1,0]
    mg_rook = [32,42,32,51,63,9,31,43, 27,32,58,62,80,55,54,15, -5,19,26,36,17,45,61,16, -24,-11,7,26,24,35,-8,-20, -36,-26,-12,1,9,-7,6,-23, -45,-25,-16,-17,3,0,-5,-33, -44,-16,-20,-9,-1,11,-6,-71, -19,-13,1,17,16,7,-37,-26]
    eg_rook = [13,10,18,15,12,12,8,5, 11,13,13,11,12,12,4,4, 7,7,7,5,4,3,7,8, 4,4,1,6,4,4,6,4, 4,5,1,3,3,2,5,4, 4,0,-2,-2,-1,2,3,4, 5,-1,0,1,1,-1,1,9, -9,-1,-3,-1,0,-2,-3,-22]
    mg_queen = [-28,0,29,12,59,44,43,45, -24,-39,-5,-9,11,59,31,78, -13,-17,7,8,29,56,47,57, -27,-27,-16,-16,-1,17,6,22, -9,-26,-9,-10,-2,-4,3,-3, -14,2,-11,-2,-5,2,14,5, -35,-8,11,2,8,15,13,1, -2,22,-8,-4,-13,23,30,-13]
    eg_queen = [-9,22,22,27,27,19,10,20, -17,20,32,41,58,25,30,0, -20,6,9,49,47,35,19,9, 3,22,24,45,57,40,57,36, -18,28,19,47,31,34,39,23, -16,-27,15,6,9,17,10,5, -22,-23,-30,-16,-16,-23,-36,-32, -33,-28,-22,-43,-5,-32,-20,-41]
    mg_king = [-65,23,16,-15,-56,-34,2,13, 29,-1,-20,-7,-8,-4,-38,-29, -9,24,2,-16,-20,6,22,-22, -17,-20,-12,-27,-30,-25,-14,-36, -49,-1,27,-39,-46,-44,-33,-51, -14,-14,-22,-46,-44,-30,-15,-27, 1,7,-8,-64,-43,-16,9,8, -15,36,12,-54,8,-28,24,14]
    eg_king = [-74,-35,-18,-18,-11,15,4,-17, -12,17,14,17,17,38,23,11, 10,17,23,15,20,45,44,13, -8,22,24,27,26,33,26,3, -18,-4,21,24,27,23,9,-11, -19,-3,11,21,23,16,7,-9, -27,-11,4,13,14,4,-5,-17, -53,-34,-10,-9,-9,-13,-24,-16]

    tt = {}
    nodes = 0
    
    def evaluate(self, board):
        if board.is_checkmate(): return -99999 if board.turn else 99999
        if board.is_stalemate() or board.is_insufficient_material(): return 0

        mg, eg, phase = 0, 0, 0

        # 1. Material & PeSTO
        for sq in chess.SQUARES:
            p = board.piece_at(sq)
            if not p: continue
            idx = sq ^ 56 if p.color == chess.WHITE else sq
            
            m, e = 0, 0
            if p.piece_type == chess.PAWN: m=self.mg_pawn[idx]; e=self.eg_pawn[idx]
            elif p.piece_type == chess.KNIGHT: m=self.mg_knight[idx]; e=self.eg_knight[idx]; phase+=1
            elif p.piece_type == chess.BISHOP: m=self.mg_bishop[idx]; e=self.eg_bishop[idx]; phase+=1
            elif p.piece_type == chess.ROOK: m=self.mg_rook[idx]; e=self.eg_rook[idx]; phase+=2
            elif p.piece_type == chess.QUEEN: m=self.mg_queen[idx]; e=self.eg_queen[idx]; phase+=4
            elif p.piece_type == chess.KING: m=self.mg_king[idx]; e=self.eg_king[idx]
            
            base = {1:100, 2:320, 3:330, 4:500, 5:900, 6:0}[p.piece_type]
            
            if p.color == chess.WHITE: mg+=base+m; eg+=base+e
            else: mg-=base+m; eg-=base+e

        # 2. Strategic Bonuses (Vanguard Logic)
        white_mobility = 0
        black_mobility = 0
        
        # Bishop Pair
        if len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2: mg += 30; eg += 50
        if len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2: mg -= 30; eg -= 50
        
        # Rook on Open File (No pawns in front)
        for sq in board.pieces(chess.ROOK, chess.WHITE):
            file = chess.square_file(sq)
            # Quick check if any white pawns on this file
            if not any(chess.square_file(s) == file for s in board.pieces(chess.PAWN, chess.WHITE)):
                mg += 20; eg += 20
        for sq in board.pieces(chess.ROOK, chess.BLACK):
            file = chess.square_file(sq)
            if not any(chess.square_file(s) == file for s in board.pieces(chess.PAWN, chess.BLACK)):
                mg -= 20; eg -= 20

        # King Safety (Penalty if king is exposed in middlegame)
        w_king = board.king(chess.WHITE)
        b_king = board.king(chess.BLACK)
        
        # White King Safety (Check file)
        if phase > 10: # Only in middlegame
            if not any(chess.square_file(s) == chess.square_file(w_king) for s in board.pieces(chess.PAWN, chess.WHITE)):
                mg -= 50 # Exposed King penalty
            if not any(chess.square_file(s) == chess.square_file(b_king) for s in board.pieces(chess.PAWN, chess.BLACK)):
                mg += 50

        # Tapered Eval
        phase = min(phase, 24)
        score = ((mg * phase) + (eg * (24 - phase))) / 24
        
        # Mobility Estimate (Legal moves count)
        # This is slow but effective. We add small bonus for having more options.
        score += (board.legal_moves.count() * 5) if board.turn == chess.WHITE else -(board.legal_moves.count() * 5)

        return int(score) if board.turn == chess.WHITE else int(-score)

    def score_move(self, board, move):
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            val = {1:1, 2:3, 3:3, 4:5, 5:9, 6:0}.get(victim.piece_type, 1) if victim else 1
            return 10000 + val
        if board.gives_check(move): return 5000
        # Promotion
        if move.promotion: return 4000
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

        # Null Move Pruning (Strategic skip)
        if depth >= 3 and not board.is_check() and not board.is_capture(board.peek()):
            board.push(chess.Move.null())
            score = -self.negamax(board, depth - 3, -beta, -beta + 1, start, limit)
            board.pop()
            if score >= beta: return beta

        moves = sorted(board.legal_moves, key=lambda m: self.score_move(board, m), reverse=True)
        max_score = -999999
        best_move = None

        for i, move in enumerate(moves):
            board.push(move)
            try:
                # Check Extension
                ext = 1 if board.is_check() else 0
                
                if i == 0:
                    score = -self.negamax(board, depth - 1 + ext, -beta, -alpha, start, limit)
                else:
                    # LMR (Late Move Reduction) for non-tactical moves
                    reduction = 0
                    if i > 3 and depth > 2 and not board.is_capture(move) and not board.is_check():
                        reduction = 1
                    
                    score = -self.negamax(board, depth - 1 + ext - reduction, -alpha - 1, -alpha, start, limit)
                    if reduction > 0 and score > alpha:
                        score = -self.negamax(board, depth - 1 + ext, -beta, -alpha, start, limit)
                    elif score > alpha and score < beta:
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
        self.mode, self.fen, self.brain, self.sf, self.deep = mode, fen, brain, sf_path, deep

    def run(self):
        board = chess.Board(self.fen)
        
        if self.mode == "INTERNAL":
            self.brain.nodes = 0
            self.brain.tt.clear()
            start = time.time()
            limit = 30.0 if self.deep else 3.0
            best = list(board.legal_moves)[0]
            
            # Iterative Deepening
            for d in range(1, 100):
                if time.time() - start > limit: break
                try:
                    alpha, beta = -99999, 99999
                    moves = sorted(board.legal_moves, key=lambda m: self.brain.score_move(board, m), reverse=True)
                    curr = None
                    for move in moves:
                        board.push(move)
                        try: score = -self.brain.negamax(board, d-1, -beta, -alpha, start, limit)
                        except TimeoutError: board.pop(); raise TimeoutError
                        board.pop()
                        if score > alpha: alpha=score; curr=move
                    
                    if curr:
                        best = curr
                        ev = f"{alpha/100:.2f}"
                        if abs(alpha) > 80000: ev = f"MATE {(90000-abs(alpha)+d)//2}"
                        self.update.emit({"depth": d, "score": alpha, "eval": ev, "nodes": self.brain.nodes, "pv": best.uci()})
                        if abs(alpha) > 80000: break
                except TimeoutError: break
            self.done.emit((best, "Cockchess Vanguard"))

        elif self.mode == "STOCKFISH":
            if not self.sf: self.done.emit((None, "No SF")); return
            try:
                eng = chess.engine.SimpleEngine.popen_uci(self.sf)
                # High ELO config for Stockfish
                eng.configure({"Threads": 4, "Hash": 512})
                
                target_d = 26 if self.deep else 18
                with eng.analysis(board, chess.engine.Limit(depth=target_d)) as ana:
                    for i in ana:
                        if i.get("depth",0) > target_d: break
                        if "score" in i:
                            sc = i["score"].relative
                            ev = f"MATE {sc.mate()}" if sc.is_mate() else f"{sc.score()/100:.2f}"
                            raw = 10000 if sc.is_mate() and sc.mate()>0 else (-10000 if sc.is_mate() else sc.score())
                            pv = " ".join([m.uci() for m in i.get("pv",[])[:4]])
                            self.update.emit({"depth": i.get("depth",0), "score": raw, "eval": ev, "nodes": i.get("nodes",0), "pv": pv})
                
                res = eng.play(board, chess.engine.Limit(time=0.1))
                eng.quit()
                self.done.emit((res.move, "Stockfish"))
            except Exception as e: self.done.emit((None, str(e)))

        elif self.mode == "ANALYZE":
            if self.sf:
                eng = chess.engine.SimpleEngine.popen_uci(self.sf)
                i = eng.analyse(board, chess.engine.Limit(time=1.0))
                eng.quit()
                self.done.emit((None, f"Best: {i['pv'][0].uci()}"))
            else: self.done.emit((None, "Load SF"))

# ==========================================
#  GUI
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
        super().__init__(); self.board=chess.Board(); self.brain=CockchessBrain(); self.sf=None; self.selected=None; self.thinking=False; self.mode="HvC"
        self.pgn=chess.pgn.Game(); self.node=self.pgn; self.init_ui(); self.find_sf(); self.refresh()

    def find_sf(self):
        for f in os.listdir("."):
            if "stockfish" in f.lower() and f.endswith(".exe"): self.sf=os.path.abspath(f); self.lbl_sf.setText("SF: READY"); self.lbl_sf.setStyleSheet("color:#0f0"); break

    def init_ui(self):
        self.setWindowTitle("Cockchess: Vanguard Edition"); self.setGeometry(100,100,1300,900); self.setStyleSheet("background:#181818;color:#ddd;font-family:Consolas;")
        c=QWidget(); self.setCentralWidget(c); l=QHBoxLayout(c); self.bar=EvalBar(); l.addWidget(self.bar)
        self.svg=QSvgWidget(); self.svg.setFixedSize(800,800); l.addWidget(self.svg)
        
        p=QFrame(); p.setFixedWidth(400); p.setStyleSheet("background:#222;border-radius:8px;"); pl=QVBoxLayout(p)
        pl.addWidget(QLabel("<h1>COCKCHESS VANGUARD</h1>"))
        
        btn_sf=QPushButton("📂 Load Stockfish"); btn_sf.clicked.connect(self.load_sf); pl.addWidget(btn_sf)
        self.lbl_sf=QLabel("SF: Missing"); self.lbl_sf.setStyleSheet("color:#f55"); pl.addWidget(self.lbl_sf)
        
        self.combo=QComboBox(); self.combo.addItems(["Human vs Cockchess","Human vs Stockfish","Cockchess vs Stockfish"]); self.combo.currentIndexChanged.connect(self.chg); self.combo.setStyleSheet("background:#333;padding:5px;"); pl.addWidget(self.combo)
        self.chk=QCheckBox("🚀 Deep Think (Middlegame Fix)"); self.chk.setStyleSheet("color:#CDD26A;font-weight:bold"); pl.addWidget(self.chk)
        
        row=QHBoxLayout(); self.btn_sim=QPushButton("Start Sim"); self.btn_sim.clicked.connect(self.run_bot); self.btn_sim.setStyleSheet("background:#d32f2f"); self.btn_sim.hide()
        btn_rst=QPushButton("Reset"); btn_rst.clicked.connect(self.reset); row.addWidget(btn_rst); row.addWidget(self.btn_sim); pl.addLayout(row)
        
        t=QHBoxLayout(); b1=QPushButton("PGN"); b1.clicked.connect(self.ex); b2=QPushButton("FEN"); b2.clicked.connect(self.cp); b3=QPushButton("Paste"); b3.clicked.connect(self.ps); t.addWidget(b1); t.addWidget(b2); t.addWidget(b3); pl.addLayout(t)
        
        b_c=QPushButton("Ask Coach"); b_c.setStyleSheet("background:#0277BD"); b_c.clicked.connect(self.anl); pl.addWidget(b_c)
        
        self.lbl_e=QLabel("Eval: 0.00"); self.lbl_e.setStyleSheet("font-size:20px;font-weight:bold"); pl.addWidget(self.lbl_e)
        self.lbl_i=QLabel("Info: ..."); pl.addWidget(self.lbl_i); self.lbl_p=QLabel("..."); self.lbl_p.setStyleSheet("color:#CDD26A"); pl.addWidget(self.lbl_p)
        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setStyleSheet("background:#000;font-size:11px"); pl.addWidget(self.log)
        l.addWidget(p); self.svg.mousePressEvent=self.click_board

    def load_sf(self): f,_=QFileDialog.getOpenFileName(self,"SF"); 
    if f: self.sf=f; self.lbl_sf.setText("SF: READY"); self.lbl_sf.setStyleSheet("color:#0f0")
    def chg(self): self.mode=["HvC","HvS","CvS"][self.combo.currentIndex()]; self.btn_sim.setVisible(self.mode=="CvS"); self.reset()
    def reset(self): self.board.reset(); self.pgn=chess.pgn.Game(); self.node=self.pgn; self.brain.tt.clear(); self.log.clear(); self.bar.set_val(0); self.refresh()
    def ex(self): pyperclip.copy(str(self.pgn)); self.log.append("PGN Copied")
    def cp(self): pyperclip.copy(self.board.fen()); self.log.append("FEN Copied")
    def ps(self): t,o=QInputDialog.getText(self,"Imp","FEN:"); 
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
    def anl(self): self.worker=EngineWorker("ANALYZE",self.board.fen(),self.brain,self.sf,False); self.worker.done.connect(lambda d: self.log.append(d[1])); self.worker.start()

if __name__ == "__main__": app=QApplication(sys.argv); w=MainWindow(); w.show(); sys.exit(app.exec_())
