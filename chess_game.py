import pygame
import chess
import sys
import time
import queue
import threading
import math
import random
import array
import socket

# ==========================================
# 1. ГЕНЕРАТОР ЗВУКА (Синтезатор)
# ==========================================

class SoundManager:
    def __init__(self):
        self.enabled = True
        self.volume = 0.5
        self.sounds = {}
        self.init_mixer()
        self.generate_sounds()
    
    def init_mixer(self):
        try:
            pygame.mixer.quit()
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        except:
            self.enabled = False
    
    def generate_beep(self, frequency=440, duration=0.1):
        try:
            sample_rate = 22050
            n_samples = int(duration * sample_rate)
            max_amplitude = 2 ** 15 - 1
            samples = array.array('h')
            for i in range(n_samples):
                envelope = 1.0 - (i / n_samples) * 0.5
                value = int(max_amplitude * 0.3 * envelope * math.sin(2.0 * math.pi * frequency * i / sample_rate))
                samples.append(value)
                samples.append(value)
            return pygame.mixer.Sound(buffer=samples)
        except:
            return None
    
    def generate_sounds(self):
        if not self.enabled: return
        try:
            self.sounds['move'] = self.generate_beep(523, 0.08)
            self.sounds['capture'] = self.generate_beep(349, 0.12)
            self.sounds['check'] = self.generate_beep(880, 0.15)
            self.sounds['checkmate'] = self.generate_beep(440, 0.25)
            self.sounds['castle'] = self.generate_beep(392, 0.1)
            self.sounds['promotion'] = self.generate_beep(659, 0.15)
            self.sounds['game_start'] = self.generate_beep(523, 0.12)
        except: self.enabled = False
    
    def play(self, sound_name):
        if not self.enabled or sound_name not in self.sounds: return
        try:
            self.sounds[sound_name].set_volume(self.volume)
            self.sounds[sound_name].play()
        except: pass
    
    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled

# ==========================================
# 2. СЕТЕВОЙ МЕНЕДЖЕР (LAN)
# ==========================================

class NetworkManager:
    def __init__(self, game_instance):
        self.game = game_instance
        self.client_socket = None
        self.connected = False
        self.running = True

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def host_game(self, port=5555):
        def server_thread():
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.bind(('0.0.0.0', port))
                server.listen(1)
                conn, addr = server.accept()
                self.client_socket = conn
                self.connected = True
                self.game.network_queue.put("HOST_READY")
                self.start_receiving()
            except: pass
        threading.Thread(target=server_thread, daemon=True).start()

    def connect_to_game(self, ip, port=5555):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            self.connected = True
            self.game.network_queue.put("CLIENT_READY")
            self.start_receiving()
            return True
        except: return False

    def send_move(self, move_uci):
        if self.connected and self.client_socket:
            try: self.client_socket.send(move_uci.encode('utf-8'))
            except: self.connected = False

    def start_receiving(self):
        threading.Thread(target=self.receive_loop, daemon=True).start()

    def receive_loop(self):
        while self.running and self.connected:
            try:
                data = self.client_socket.recv(1024)
                if not data: break
                self.game.network_queue.put(data.decode('utf-8'))
            except: break
        self.connected = False
        self.game.network_queue.put("DISCONNECT")

# ==========================================
# 3. ШАХМАТНЫЙ ДВИЖОК (Полный)
# ==========================================

OPENING_BOOK = {
    'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1': ['e2e4', 'd2d4', 'g1f3', 'c2c4'],
    'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1': ['e7e5', 'c7c5', 'e7e6', 'c7c6'],
    'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2': ['g1f3', 'f1c4', 'b1c3'],
    'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1': ['d7d5', 'g8f6', 'e7e6', 'c7c5'],
}

def get_opening_move(board):
    fen = board.fen()
    if fen in OPENING_BOOK:
        try: return chess.Move.from_uci(random.choice(OPENING_BOOK[fen]))
        except: pass
    return None

PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}

PAWN_TABLE = [0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10, 5,5,10,25,25,10,5,5, 0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5, 5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0]
KNIGHT_TABLE = [-50,-40,-30,-30,-30,-30,-40,-50, -40,-20,0,5,5,0,-20,-40, -30,5,10,15,15,10,5,-30, -30,0,15,20,20,15,0,-30, -30,5,15,20,20,15,5,-30, -30,0,10,15,15,10,0,-30, -40,-20,0,0,0,0,-20,-40, -50,-40,-30,-30,-30,-30,-40,-50]
BISHOP_TABLE = [-20,-10,-10,-10,-10,-10,-10,-20, -10,5,0,0,0,0,5,-10, -10,10,10,10,10,10,10,-10, -10,0,10,10,10,10,0,-10, -10,5,5,10,10,5,5,-10, -10,0,5,10,10,5,0,-10, -10,0,0,0,0,0,0,-10, -20,-10,-10,-10,-10,-10,-10,-20]
ROOK_TABLE = [0,0,0,5,5,0,0,0, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, 5,10,10,10,10,10,10,5, 0,0,0,0,0,0,0,0]
QUEEN_TABLE = [-20,-10,-10,-5,-5,-10,-10,-20, -10,0,5,0,0,0,0,-10, -10,5,5,5,5,5,0,-10, 0,0,5,5,5,5,0,-5, -5,0,5,5,5,5,0,-5, -10,0,5,5,5,5,0,-10, -10,0,0,0,0,0,0,-10, -20,-10,-10,-5,-5,-10,-10,-20]
KING_TABLE = [20,30,10,0,0,10,30,20, 20,20,0,0,0,0,20,20, -10,-20,-20,-20,-20,-20,-20,-10, -20,-30,-30,-40,-40,-30,-30,-20, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30]

TABLES = {chess.PAWN: PAWN_TABLE, chess.KNIGHT: KNIGHT_TABLE, chess.BISHOP: BISHOP_TABLE, chess.ROOK: ROOK_TABLE, chess.QUEEN: QUEEN_TABLE, chess.KING: KING_TABLE}

def evaluate_board(board):
    """
    Оценивает позицию на доске
    Положительное значение = хорошо для белых
    Отрицательное значение = хорошо для чёрных
    """
    if board.is_checkmate(): 
        return -99999 if board.turn else 99999
    if board.is_stalemate() or board.is_insufficient_material(): 
        return 0
    
    score = 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if not piece: 
            continue
        
        val = PIECE_VALUES[piece.piece_type]
        table = TABLES[piece.piece_type]
        pos = square if piece.color == chess.WHITE else chess.square_mirror(square)
        
        if piece.color == chess.WHITE: 
            score += val + table[pos]
        else: 
            score -= val + table[pos]
    
    return score


def find_best_move(board, depth):
    """
    Находит лучший ход для текущей позиции
    
    Args:
        board: Шахматная доска
        depth: Глубина поиска
        
    Returns:
        chess.Move или None если нет легальных ходов
    """
    # Проверка на наличие легальных ходов
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return None
    
    # Если всего один ход - возвращаем его
    if len(legal_moves) == 1:
        return legal_moves[0]
    
    best_move = None
    max_turn = board.turn == chess.WHITE
    best_eval = -999999 if max_turn else 999999
    alpha, beta = -999999, 999999
    
    # Упорядочиваем ходы для лучшей производительности
    moves = order_moves(board, legal_moves)
    
    for move in moves:
        board.push(move)
        eval_score = minimax(board, depth-1, alpha, beta, not max_turn)
        board.pop()
        
        if max_turn:
            if eval_score > best_eval:
                best_eval = eval_score
                best_move = move
            alpha = max(alpha, eval_score)
        else:
            if eval_score < best_eval:
                best_eval = eval_score
                best_move = move
            beta = min(beta, eval_score)
        
        # Alpha-beta отсечение
        if beta <= alpha:
            break
    
    return best_move

def order_moves(board, moves):
    def score(m):
        if board.is_capture(m):
            attacker = board.piece_at(m.from_square)
            victim = board.piece_at(m.to_square)
            if attacker and victim:
                return PIECE_VALUES[victim.piece_type]*10 - PIECE_VALUES[attacker.piece_type]
        if board.gives_check(m): return 500
        if m.promotion: return 800
        return 0
    return sorted(moves, key=score, reverse=True)

def minimax(board, depth, alpha, beta, maximizing):
    if depth == 0 or board.is_game_over(): return evaluate_board(board)
    moves = order_moves(board, list(board.legal_moves))
    if maximizing:
        max_eval = -999999
        for move in moves:
            board.push(move)
            eval = minimax(board, depth-1, alpha, beta, False)
            board.pop()
            max_eval = max(max_eval, eval)
            alpha = max(alpha, eval)
            if beta <= alpha: break
        return max_eval
    else:
        min_eval = 999999
        for move in moves:
            board.push(move)
            eval = minimax(board, depth-1, alpha, beta, True)
            board.pop()
            min_eval = min(min_eval, eval)
            beta = min(beta, eval)
            if beta <= alpha: break
        return min_eval

def find_best_move(board, depth):
    """
    Находит лучший ход для текущей позиции
    
    Args:
        board: Шахматная доска
        depth: Глубина поиска
        
    Returns:
        chess.Move или None если нет легальных ходов
    """
    # Проверка на наличие легальных ходов
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return None
    
    # Если всего один ход - возвращаем его
    if len(legal_moves) == 1:
        return legal_moves[0]
    
    best_move = None
    max_turn = board.turn == chess.WHITE
    best_eval = -999999 if max_turn else 999999
    alpha, beta = -999999, 999999
    
    # Упорядочиваем ходы для лучшей производительности
    moves = order_moves(board, legal_moves)
    
    for move in moves:
        board.push(move)
        eval_score = minimax(board, depth-1, alpha, beta, not max_turn)
        board.pop()
        
        if max_turn:
            if eval_score > best_eval:
                best_eval = eval_score
                best_move = move
            alpha = max(alpha, eval_score)
        else:
            if eval_score < best_eval:
                best_eval = eval_score
                best_move = move
            beta = min(beta, eval_score)
        
        # Alpha-beta отсечение
        if beta <= alpha:
            break
    
    return best_move

# ==========================================
# 4. ИНТЕРФЕЙС
# ==========================================

WIDTH, HEIGHT = 1100, 750
BOARD_SIZE = 640
SQUARE_SIZE = BOARD_SIZE // 8
BOARD_X, BOARD_Y = 30, 30
PANEL_X = BOARD_X + BOARD_SIZE + 30
PANEL_WIDTH = WIDTH - PANEL_X - 20
FPS = 60

THEMES = [
    {"name": "Классика", "light": (238,238,210), "dark": (118,150,86), "highlight": (186,202,68)},
    {"name": "Океан", "light": (230,230,240), "dark": (100,130,180), "highlight": (130,160,210)},
    {"name": "Дерево", "light": (240,217,181), "dark": (181,136,99), "highlight": (205,210,106)},
    {"name": "Металл", "light": (220,220,220), "dark": (120,120,120), "highlight": (180,180,180)},
]

WHITE_COL = (245,245,245)
BG_COLOR = (40,40,45)
PANEL_COLOR = (50,50,55)
BUTTON_COLOR = (70,70,80)
BUTTON_HOVER = (90,90,100)
BUTTON_ACTIVE = (60,120,60)
INPUT_BG = (30,30,35)

class Button:
    def __init__(self, x, y, w, h, text, color=BUTTON_COLOR):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.hover_color = (min(color[0]+20,255), min(color[1]+20,255), min(color[2]+20,255))
        self.disabled = False
    
    def draw(self, screen, font):
        pos = pygame.mouse.get_pos()
        color = self.hover_color if self.rect.collidepoint(pos) and not self.disabled else self.color
        if self.disabled: color = (50,50,50)
        pygame.draw.rect(screen, color, self.rect, border_radius=8)
        pygame.draw.rect(screen, (100,100,110), self.rect, 2, border_radius=8)
        text_surf = font.render(self.text, True, WHITE_COL if not self.disabled else (100,100,100))
        screen.blit(text_surf, text_surf.get_rect(center=self.rect.center))
    
    def is_clicked(self, pos):
        return self.rect.collidepoint(pos) and not self.disabled

class InputBox:
    def __init__(self, x, y, w, h, text=''):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = (100,100,100)
        self.text = text
        self.active = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            self.color = (100,200,100) if self.active else (100,100,100)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN: pass
            elif event.key == pygame.K_BACKSPACE: self.text = self.text[:-1]
            else: self.text += event.unicode

    def draw(self, screen, font):
        txt = font.render(self.text, True, WHITE_COL)
        pygame.draw.rect(screen, INPUT_BG, self.rect)
        pygame.draw.rect(screen, self.color, self.rect, 2)
        screen.blit(txt, (self.rect.x+5, self.rect.y+8))

class ChessGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF)
        pygame.display.set_caption("Шахматы v22.1 (Full Logic + LAN + Promotion)")
        self.clock = pygame.time.Clock()
        
        self.sound_manager = SoundManager()
        self.network = NetworkManager(self)
        self.network_queue = queue.Queue()
        self.board = chess.Board()
        
        self.ai_depth = 3
        self.selected_square = None
        self.is_thinking = False
        self.game_status = "Меню"
        self.history = []
        self.game_over_flag = False
        self.state = "MENU"
        self.player_side = chess.WHITE
        self.current_theme_idx = 0
        self.animation_speed = 0.5
        self.last_eval = 0
        
        self.show_hints = False
        self.hint_moves = []
        self.is_calculating_hints = False
        self.timer_enabled = False
        self.timer_running = False
        self.time_white = 0
        self.time_black = 0
        self.last_timer_update = 0
        self.is_lan_mode = False
        
        self.ai_queue = queue.Queue()
        self.hint_queue = queue.Queue()
        
        # Диалог превращения пешки
        self.promotion_dialog = None
        self.pending_promotion_move = None
        
        try:
            self.font_pieces = pygame.font.SysFont("segoeuisymbol", int(SQUARE_SIZE * 0.8))
            self.font_ui = pygame.font.SysFont("arial", 18, bold=True)
            self.font_title = pygame.font.SysFont("arial", 32, bold=True)
            self.font_small = pygame.font.SysFont("arial", 14)
            self.font_coord = pygame.font.SysFont("arial", 13, bold=True)
        except:
            self.font_pieces = pygame.font.SysFont("arial", int(SQUARE_SIZE * 0.8))
            self.font_ui = pygame.font.SysFont("arial", 18)
            self.font_title = pygame.font.SysFont("arial", 32)
            self.font_small = pygame.font.SysFont("arial", 14)
            self.font_coord = pygame.font.SysFont("arial", 13)
        
        self.pieces_symbols = {'r':'♜', 'n':'♞', 'b':'♝', 'q':'♛', 'k':'♚', 'p':'♟',
                               'R':'♖', 'N':'♘', 'B':'♗', 'Q':'♕', 'K':'♔', 'P':'♙'}
        
        self.init_ui()

    def init_ui(self):
        cy = HEIGHT // 2
        # Кнопки Одиночной игры (Слева)
        self.menu_btn_white = Button(WIDTH//2-250, cy-140, 240, 50, "С ИИ (Белые)")
        self.menu_btn_black = Button(WIDTH//2-250, cy-80, 240, 50, "С ИИ (Черные)")
        
        # Таймеры
        self.menu_btn_no_timer = Button(WIDTH//2-250, cy-20, 70, 40, "∞")
        self.menu_btn_blitz = Button(WIDTH//2-170, cy-20, 70, 40, "3 мин")
        self.menu_btn_rapid = Button(WIDTH//2-90, cy-20, 80, 40, "10 мин")
        
        # Сетевые кнопки (Справа)
        self.input_ip = InputBox(WIDTH//2+20, cy-140, 200, 40, "127.0.0.1")
        self.menu_btn_host = Button(WIDTH//2+20, cy-80, 200, 50, "Создать (Хост)", (60, 100, 120))
        self.menu_btn_connect = Button(WIDTH//2+20, cy-20, 200, 50, "Подключиться", (60, 120, 100))
        
        self.menu_btn_quit = Button(WIDTH//2-100, cy+150, 200, 50, "Выход", (120,60,60))
        
        # Панель
        y, w, h, gap = 60, PANEL_WIDTH-20, 38, 8
        self.btn_hint = Button(PANEL_X+10, y, w, h, "💡 Подсказка"); y += h + gap
        self.btn_undo = Button(PANEL_X+10, y, w, h, "↶ Отменить"); y += h + gap
        self.btn_new = Button(PANEL_X+10, y, w, h, "🏠 Меню"); y += h + gap*2
        bw = (w-10)//2
        self.btn_theme = Button(PANEL_X+10, y, bw, h, "🎨 Тема")
        self.btn_sound = Button(PANEL_X+10+bw+10, y, bw, h, "🔊 Звук")
        y += h + gap
        self.btn_level_down = Button(PANEL_X+10, y, 40, h, "-")
        self.btn_level_up = Button(PANEL_X+10+w-40, y, 40, h, "+")
        
        self.btn_quit = Button(PANEL_X+10, HEIGHT-70, w, h, "✕ Выход", (120,60,60))
        self.go_btn_menu = Button(WIDTH//2-150, HEIGHT//2+85, 300, 50, "В МЕНЮ")

    def to_screen(self, sq):
        col, row = chess.square_file(sq), 7 - chess.square_rank(sq)
        if self.player_side == chess.BLACK: col, row = 7-col, 7-row
        return BOARD_X + col*SQUARE_SIZE, BOARD_Y + row*SQUARE_SIZE
    
    def from_screen(self, x, y):
        col, row = (x-BOARD_X)//SQUARE_SIZE, (y-BOARD_Y)//SQUARE_SIZE
        if self.player_side == chess.BLACK: col, row = 7-col, 7-row
        return chess.square(col, 7-row)

    def start_game(self, color, mode="AI"):
        self.board = chess.Board()
        self.selected_square = None
        self.history = []
        self.game_over_flag = False
        self.player_side = color
        self.state = "PLAYING"
        self.last_eval = 0
        self.is_lan_mode = (mode == "LAN")
        self.show_hints = False
        self.hint_moves = []
        self.promotion_dialog = None
        self.pending_promotion_move = None
        
        # Таймер
        if self.timer_enabled:
            if self.timer_mode == "blitz": self.time_white = self.time_black = 180
            else: self.time_white = self.time_black = 600
            self.timer_running = True
            self.last_timer_update = time.time()
        else: self.timer_running = False
        
        self.sound_manager.play('game_start')
        
        if self.is_lan_mode:
            self.game_status = "Игра по сети"
        else:
            if color == chess.WHITE: self.game_status = "Ваш ход"
            else:
                self.game_status = "ИИ думает..."
                self.is_thinking = True
                threading.Thread(target=self.run_ai, daemon=True).start()

    def draw_board(self):
        theme = THEMES[self.current_theme_idx]
        light, dark, highlight = theme["light"], theme["dark"], theme["highlight"]
        
        for i in range(8):
            num = str(i+1) if self.player_side == chess.BLACK else str(8-i)
            lbl = self.font_coord.render(num, True, (180,180,180))
            self.screen.blit(lbl, (BOARD_X-18, BOARD_Y+i*SQUARE_SIZE+SQUARE_SIZE//2-8))
            let = "HGFEDCBA" if self.player_side == chess.BLACK else "ABCDEFGH"
            lbl2 = self.font_coord.render(let[i], True, (180,180,180))
            self.screen.blit(lbl2, (BOARD_X+i*SQUARE_SIZE+SQUARE_SIZE//2-5, BOARD_Y+BOARD_SIZE+5))

        for r in range(8):
            for c in range(8):
                color = light if (r+c)%2==0 else dark
                pygame.draw.rect(self.screen, color, (BOARD_X+c*SQUARE_SIZE, BOARD_Y+r*SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE))
        
        if len(self.board.move_stack) > 0:
            last = self.board.peek()
            for sq in [last.from_square, last.to_square]:
                x, y = self.to_screen(sq)
                s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
                s.set_alpha(140)
                s.fill(highlight)
                self.screen.blit(s, (x,y))
        
        if self.selected_square is not None:
            x, y = self.to_screen(self.selected_square)
            pygame.draw.rect(self.screen, (255,255,0), (x, y, SQUARE_SIZE, SQUARE_SIZE), 5)
            for move in self.board.legal_moves:
                if move.from_square == self.selected_square:
                    tx, ty = self.to_screen(move.to_square)
                    cx, cy = tx+SQUARE_SIZE//2, ty+SQUARE_SIZE//2
                    if self.board.piece_at(move.to_square): pygame.draw.circle(self.screen, (200,80,80), (cx,cy), SQUARE_SIZE//2-5, 5)
                    else: pygame.draw.circle(self.screen, (60,60,60,100), (cx,cy), SQUARE_SIZE//6)
        
        if self.show_hints and self.hint_moves:
            for i, move in enumerate(self.hint_moves[:3]):
                fx, fy = self.to_screen(move.from_square)
                tx, ty = self.to_screen(move.to_square)
                col = [(50,255,50), (150,255,50), (255,255,50)][i]
                pygame.draw.line(self.screen, col, (fx+SQUARE_SIZE//2, fy+SQUARE_SIZE//2), (tx+SQUARE_SIZE//2, ty+SQUARE_SIZE//2), 5)

        if self.board.is_check():
            k = self.board.king(self.board.turn)
            if k is not None:
                x, y = self.to_screen(k)
                pygame.draw.rect(self.screen, (255,80,80), (x, y, SQUARE_SIZE, SQUARE_SIZE), 6)

    def draw_pieces(self, skip=None):
        for sq in chess.SQUARES:
            if sq == skip: continue
            piece = self.board.piece_at(sq)
            if piece:
                x, y = self.to_screen(sq)
                sym = self.pieces_symbols[piece.symbol()]
                col = WHITE_COL if piece.color == chess.WHITE else (10,10,10)
                txt = self.font_pieces.render(sym, True, col)
                r = txt.get_rect(center=(x+SQUARE_SIZE//2, y+SQUARE_SIZE//2))
                shad = self.font_pieces.render(sym, True, (50,50,50) if piece.color==chess.WHITE else (200,200,200))
                off = (2,2) if piece.color==chess.WHITE else (-1,-1)
                self.screen.blit(shad, (r.x+off[0], r.y+off[1]))
                self.screen.blit(txt, r)

    def draw_promotion_dialog(self):
        """Диалог выбора фигуры при превращении пешки"""
        if not self.promotion_dialog:
            return
        
        # Затемнение фона
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        # Параметры диалога
        dialog_w, dialog_h = 400, 200
        dialog_x = (WIDTH - dialog_w) // 2
        dialog_y = (HEIGHT - dialog_h) // 2
        
        # Фон диалога
        pygame.draw.rect(self.screen, PANEL_COLOR, (dialog_x, dialog_y, dialog_w, dialog_h), border_radius=15)
        pygame.draw.rect(self.screen, (100, 100, 110), (dialog_x, dialog_y, dialog_w, dialog_h), 3, border_radius=15)
        
        # Заголовок
        title = self.font_title.render("Выберите фигуру", True, WHITE_COL)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, dialog_y + 40)))
        
        # Кнопки с фигурами
        piece_types = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]
        piece_symbols = ['♕', '♖', '♗', '♘'] if self.board.turn == chess.WHITE else ['♛', '♜', '♝', '♞']
        button_size = 70
        spacing = 20
        start_x = dialog_x + (dialog_w - (button_size * 4 + spacing * 3)) // 2
        button_y = dialog_y + 90
        
        for i, (piece_type, symbol) in enumerate(zip(piece_types, piece_symbols)):
            btn_x = start_x + i * (button_size + spacing)
            btn_rect = pygame.Rect(btn_x, button_y, button_size, button_size)
            
            # Проверка наведения мыши
            mouse_pos = pygame.mouse.get_pos()
            color = BUTTON_HOVER if btn_rect.collidepoint(mouse_pos) else BUTTON_COLOR
            
            pygame.draw.rect(self.screen, color, btn_rect, border_radius=10)
            pygame.draw.rect(self.screen, (100, 100, 110), btn_rect, 2, border_radius=10)
            
            # Рисуем фигуру
            piece_text = self.font_pieces.render(symbol, True, WHITE_COL if self.board.turn == chess.WHITE else (10, 10, 10))
            text_rect = piece_text.get_rect(center=btn_rect.center)
            self.screen.blit(piece_text, text_rect)
            
            # Сохраняем rect для обработки кликов
            self.promotion_dialog['buttons'][piece_type] = btn_rect

    def draw_panel(self):
        pygame.draw.rect(self.screen, PANEL_COLOR, (PANEL_X-10, 0, PANEL_WIDTH+20, HEIGHT))
        title = self.font_title.render("Chess v22", True, WHITE_COL)
        self.screen.blit(title, (PANEL_X+60, 15))
        
        # Таймеры
        if self.timer_enabled:
            mins_b, secs_b = divmod(int(self.time_black), 60)
            mins_w, secs_w = divmod(int(self.time_white), 60)
            col_b = (255,100,100) if self.time_black<30 else (200,200,200)
            col_w = (255,100,100) if self.time_white<30 else (200,200,200)
            if not self.board.turn: col_b = (255,255,150)
            else: col_w = (255,255,150)
            
            tb = self.font_ui.render(f"⚫ {mins_b}:{secs_b:02d}", True, col_b)
            tw = self.font_ui.render(f"⚪ {mins_w}:{secs_w:02d}", True, col_w)
            self.screen.blit(tb, (PANEL_X+20, 60))
            self.screen.blit(tw, (PANEL_X+20, 90))
            base_y = 130
        else: base_y = 60

        st_col = (150, 255, 150) if not "МАТ" in self.game_status else (255,100,100)
        st = self.font_ui.render(self.game_status[:25], True, st_col)
        self.screen.blit(st, (PANEL_X+10, base_y)) 
        
        # Кнопки
        self.btn_hint.rect.y = base_y + 40
        self.btn_undo.rect.y = base_y + 86
        self.btn_new.rect.y = base_y + 132
        self.btn_theme.rect.y = base_y + 178
        self.btn_sound.rect.y = base_y + 178
        self.btn_level_down.rect.y = base_y + 224
        self.btn_level_up.rect.y = base_y + 224
        
        self.btn_hint.text = "💡 Думаю..." if self.is_calculating_hints else ("💡 Скрыть" if self.show_hints else "💡 Подсказка")
        self.btn_sound.text = "🔊 ВКЛ" if self.sound_manager.enabled else "🔇 ВЫКЛ"
        
        self.btn_hint.draw(self.screen, self.font_ui)
        self.btn_undo.draw(self.screen, self.font_ui)
        self.btn_new.draw(self.screen, self.font_ui)
        self.btn_theme.draw(self.screen, self.font_ui)
        self.btn_sound.draw(self.screen, self.font_ui)
        
        lvl = self.font_small.render(f"Уровень: {self.ai_depth}", True, WHITE_COL)
        self.screen.blit(lvl, (PANEL_X+65, base_y+234))
        self.btn_level_down.draw(self.screen, self.font_ui)
        self.btn_level_up.draw(self.screen, self.font_ui)
        
        # История
        y = base_y + 280
        hist_lbl = self.font_ui.render("История:", True, (200,200,200))
        self.screen.blit(hist_lbl, (PANEL_X+10, y))
        for move in self.history[-6:]:
            y += 20
            t = self.font_small.render(move, True, (200,200,200))
            self.screen.blit(t, (PANEL_X+15, y))

        self.btn_quit.draw(self.screen, self.font_ui)

    def draw_menu(self):
        self.screen.fill(BG_COLOR)
        title = self.font_title.render("ШАХМАТЫ", True, WHITE_COL)
        self.screen.blit(title, title.get_rect(center=(WIDTH//2, 80)))
        
        # Левая колонка
        lbl_ai = self.font_ui.render("ОДИНОЧНАЯ ИГРА", True, (200,200,200))
        self.screen.blit(lbl_ai, (WIDTH//2-230, HEIGHT//2-160))
        self.menu_btn_white.draw(self.screen, self.font_ui)
        self.menu_btn_black.draw(self.screen, self.font_ui)
        
        if not self.timer_enabled: self.menu_btn_no_timer.color = BUTTON_ACTIVE
        else: self.menu_btn_no_timer.color = BUTTON_COLOR
        if self.timer_enabled and self.timer_mode=="blitz": self.menu_btn_blitz.color = BUTTON_ACTIVE
        else: self.menu_btn_blitz.color = BUTTON_COLOR
        if self.timer_enabled and self.timer_mode=="rapid": self.menu_btn_rapid.color = BUTTON_ACTIVE
        else: self.menu_btn_rapid.color = BUTTON_COLOR
        
        self.menu_btn_no_timer.draw(self.screen, self.font_ui)
        self.menu_btn_blitz.draw(self.screen, self.font_ui)
        self.menu_btn_rapid.draw(self.screen, self.font_ui)
        
        # Правая колонка
        lbl_lan = self.font_ui.render("СЕТЕВАЯ ИГРА (LAN)", True, (100,200,255))
        self.screen.blit(lbl_lan, (WIDTH//2+40, HEIGHT//2-160))
        ip_txt = self.font_small.render(f"Ваш IP: {self.network.get_local_ip()}", True, (150,150,150))
        self.screen.blit(ip_txt, (WIDTH//2+20, HEIGHT//2-135))
        self.input_ip.draw(self.screen, self.font_ui)
        self.menu_btn_host.draw(self.screen, self.font_ui)
        self.menu_btn_connect.draw(self.screen, self.font_ui)
        
        self.menu_btn_quit.draw(self.screen, self.font_ui)

    def animate_move(self, move):
        fx, fy = self.to_screen(move.from_square)
        tx, ty = self.to_screen(move.to_square)
        piece = self.board.piece_at(move.from_square)
        if not piece: return
        pygame.event.pump()
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > self.animation_speed: break
            progress = math.sin(min(1.0, elapsed/self.animation_speed) * math.pi/2)
            cx, cy = fx + (tx-fx)*progress, fy + (ty-fy)*progress
            
            self.screen.fill(BG_COLOR)
            self.draw_board()
            self.draw_pieces(skip=move.from_square)
            self.draw_panel()
            
            sym = self.pieces_symbols[piece.symbol()]
            col = WHITE_COL if piece.color == chess.WHITE else (10,10,10)
            txt = self.font_pieces.render(sym, True, col)
            self.screen.blit(txt, txt.get_rect(center=(cx+SQUARE_SIZE//2, cy+SQUARE_SIZE//2)))
            pygame.display.flip()
            self.clock.tick(60)

    def undo_move(self):
        if self.is_thinking or len(self.history) == 0: return
        if self.is_lan_mode: return 
        
        if len(self.board.move_stack) > 0:
            self.board.pop(); self.history.pop()
        if len(self.board.move_stack) > 0:
            self.board.pop(); self.history.pop()
        
        self.selected_square = None
        self.game_over_flag = False
        self.game_status = "Ваш ход"
        self.show_hints = False
        self.hint_moves = []

    def calculate_hints(self):
        try:
            moves = order_moves(self.board, list(self.board.legal_moves))
            scored = []
            for m in moves[:6]:
                self.board.push(m)
                s = minimax(self.board, self.ai_depth-1, -999999, 999999, not self.board.turn)
                self.board.pop()
                scored.append((m, s))
            scored.sort(key=lambda x: x[1], reverse=(self.board.turn==chess.WHITE))
            self.hint_queue.put([x[0] for x in scored[:3]])
        except: pass

    def execute_move(self, move):
        if self.is_lan_mode and self.board.turn == self.player_side:
            self.network.send_move(move.uci())
        
        if self.timer_enabled: self.timer_running = False
            
        capture = self.board.is_capture(move)
        is_promotion = move.promotion is not None
        
        self.animate_move(move)
        self.board.push(move)
        self.history.append(move.uci())
        self.selected_square = None
        self.show_hints = False
        self.hint_moves = []
        
        if self.board.is_checkmate():
            self.sound_manager.play('checkmate')
            self.game_over_flag = True
            self.game_status = "МАТ! Игра окончена."
        elif self.board.is_check():
            self.sound_manager.play('check')
            self.game_status = "ШАХ!"
            if self.timer_enabled and not self.game_over_flag:
                self.timer_running = True
                self.last_timer_update = time.time()
        else:
            if is_promotion:
                self.sound_manager.play('promotion')
            else:
                self.sound_manager.play('capture' if capture else 'move')
            if self.timer_enabled and not self.game_over_flag:
                self.timer_running = True
                self.last_timer_update = time.time()

        if not self.is_lan_mode and not self.game_over_flag and self.board.turn != self.player_side:
            self.is_thinking = True
            self.game_status = "ИИ думает..."
            threading.Thread(target=self.run_ai, daemon=True).start()
        elif self.is_lan_mode and not self.game_over_flag:
            if self.board.turn == self.player_side: self.game_status = "Ваш ход"
            else: self.game_status = "Ход противника"

    def run_ai(self):
        try:
            op = get_opening_move(self.board.copy())
            best = op if op else find_best_move(self.board.copy(), self.ai_depth)
            if best: self.ai_queue.put(best)
        except: pass

    def handle_click(self, pos):
        if self.state == "MENU":
            self.input_ip.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos))
            if self.menu_btn_white.is_clicked(pos): self.start_game(chess.WHITE, "AI")
            elif self.menu_btn_black.is_clicked(pos): self.start_game(chess.BLACK, "AI")
            elif self.menu_btn_no_timer.is_clicked(pos): self.timer_enabled = False
            elif self.menu_btn_blitz.is_clicked(pos): self.timer_enabled = True; self.timer_mode = "blitz"
            elif self.menu_btn_rapid.is_clicked(pos): self.timer_enabled = True; self.timer_mode = "rapid"
            
            elif self.menu_btn_host.is_clicked(pos):
                self.network.host_game()
                self.game_status = "Ожидание игрока..."
            elif self.menu_btn_connect.is_clicked(pos):
                if self.network.connect_to_game(self.input_ip.text): pass
            elif self.menu_btn_quit.is_clicked(pos): pygame.quit(); sys.exit()
            return
        
        # Обработка диалога превращения пешки
        if self.promotion_dialog:
            for piece_type, btn_rect in self.promotion_dialog['buttons'].items():
                if btn_rect.collidepoint(pos):
                    move = self.pending_promotion_move
                    move.promotion = piece_type
                    self.execute_move(move)
                    self.promotion_dialog = None
                    self.pending_promotion_move = None
                    return
        
        # Кнопки панели
        if self.btn_new.is_clicked(pos): self.state = "MENU"; self.network.connected = False
        elif self.btn_theme.is_clicked(pos): self.current_theme_idx = (self.current_theme_idx+1)%len(THEMES)
        elif self.btn_sound.is_clicked(pos): self.sound_manager.toggle()
        elif self.btn_undo.is_clicked(pos): self.undo_move()
        elif self.btn_hint.is_clicked(pos):
            if self.show_hints: self.show_hints = False
            else:
                self.is_calculating_hints = True
                threading.Thread(target=self.calculate_hints, daemon=True).start()
        elif self.btn_level_down.is_clicked(pos): self.ai_depth = max(1, self.ai_depth-1)
        elif self.btn_level_up.is_clicked(pos): self.ai_depth = min(6, self.ai_depth+1)
        elif self.game_over_flag and self.go_btn_menu.is_clicked(pos): self.state = "MENU"
        elif self.btn_quit.is_clicked(pos): pygame.quit(); sys.exit()
        
        if self.is_thinking or self.game_over_flag: return
        if self.is_lan_mode and self.board.turn != self.player_side: return
        if pos[0] < BOARD_X or pos[0] > BOARD_X+BOARD_SIZE or pos[1] < BOARD_Y or pos[1] > BOARD_Y+BOARD_SIZE: return
        sq = self.from_screen(pos[0], pos[1])
        
        if self.selected_square is None:
            p = self.board.piece_at(sq)
            if p and p.color == self.board.turn:
                if self.is_lan_mode and p.color != self.player_side: return
                self.selected_square = sq
        else:
            move = chess.Move(self.selected_square, sq)
            p = self.board.piece_at(self.selected_square)
            
            # Проверка на превращение пешки
            if p and p.piece_type == chess.PAWN:
                if (p.color and chess.square_rank(sq)==7) or (not p.color and chess.square_rank(sq)==0):
                    # Проверяем что это легальный ход
                    for legal_move in self.board.legal_moves:
                        if legal_move.from_square == self.selected_square and legal_move.to_square == sq:
                            # Показываем диалог выбора фигуры
                            self.pending_promotion_move = move
                            self.promotion_dialog = {'buttons': {}}
                            self.selected_square = None
                            return
            
            if move in self.board.legal_moves: 
                self.execute_move(move)
            else:
                p = self.board.piece_at(sq)
                if p and p.color == self.board.turn: self.selected_square = sq
                else: self.selected_square = None

    def run(self):
        while True:
            self.clock.tick(FPS)
            
            # Таймер
            if self.timer_enabled and self.timer_running and not self.game_over_flag:
                now = time.time()
                elapsed = now - self.last_timer_update
                self.last_timer_update = now
                if self.board.turn == chess.WHITE: self.time_white -= elapsed
                else: self.time_black -= elapsed
                if self.time_white <= 0 or self.time_black <= 0:
                    self.game_over_flag = True
                    self.game_status = "Время вышло!"
                    self.sound_manager.play('checkmate')

            # События из очередей
            if not self.ai_queue.empty():
                m = self.ai_queue.get()
                pygame.event.pump(); time.sleep(0.1)
                self.execute_move(m)
                self.is_thinking = False
            
            if not self.hint_queue.empty():
                self.hint_moves = self.hint_queue.get()
                self.show_hints = True
                self.is_calculating_hints = False

            if not self.network_queue.empty():
                msg = self.network_queue.get()
                if msg == "HOST_READY": self.start_game(chess.WHITE, "LAN")
                elif msg == "CLIENT_READY": self.start_game(chess.BLACK, "LAN")
                elif msg == "DISCONNECT": self.game_status = "Связь разорвана"
                else:
                    try:
                        m = chess.Move.from_uci(msg)
                        if m in self.board.legal_moves:
                            self.animate_move(m)
                            self.board.push(m)
                            self.history.append(m.uci())
                            self.sound_manager.play('move')
                            self.game_status = "Ваш ход"
                    except: pass

            if self.state == "MENU":
                self.draw_menu()
                for e in pygame.event.get():
                    if e.type == pygame.QUIT: pygame.quit(); sys.exit()
                    self.input_ip.handle_event(e)
                    if e.type == pygame.MOUSEBUTTONDOWN: self.handle_click(e.pos)
            else:
                self.screen.fill(BG_COLOR)
                self.draw_board()
                self.draw_pieces()
                self.draw_panel()
                
                # Диалог превращения пешки
                if self.promotion_dialog:
                    self.draw_promotion_dialog()
                
                if self.game_over_flag:
                    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0,0,0,180))
                    self.screen.blit(overlay, (0,0))
                    txt = self.font_title.render(self.game_status, True, (255,200,100))
                    self.screen.blit(txt, txt.get_rect(center=(WIDTH//2, HEIGHT//2-50)))
                    self.go_btn_menu.draw(self.screen, self.font_ui)
                for e in pygame.event.get():
                    if e.type == pygame.QUIT: pygame.quit(); sys.exit()
                    if e.type == pygame.MOUSEBUTTONDOWN: self.handle_click(e.pos)
            pygame.display.flip()

if __name__ == "__main__":
    game = ChessGame()
    game.run()