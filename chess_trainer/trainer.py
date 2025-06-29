#!/usr/bin/env python3
import os

try:  # optional dependency for .env support
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    def load_dotenv() -> None:
        pass

try:  # optional network dependency
    import berserk
except Exception:  # pragma: no cover - optional dependency
    berserk = None

try:  # optional chess engine library
    import chess
    import chess.engine
except Exception:  # pragma: no cover - optional dependency
    chess = None
from dataclasses import dataclass, field
from typing import List

load_dotenv()  # read token from environment if available
API_TOKEN = os.getenv("LICHESS_BOT_TOKEN")

"""Main bot training loop and event handling."""

from . import openings_explorer

STOCKFISH_PATH = "/usr/games/stockfish"
# TODO check if the binary actually exists in this path, if not, do "which stockfish" and use that path instead

OUR_NAME = "chess-trainer-bot" # to identify our name on Lichess
TIME_PER_MOVE = 5
# CHALLENGE = 100 # how much to increase bot ELO compared to player's

if berserk is not None and API_TOKEN:
    session = berserk.TokenSession(API_TOKEN)
    client = berserk.Client(session=session)
else:  # pragma: no cover - allows running tests without optional deps
    session = client = None

white_openings = ["e4 - King's Pawn Game",
                  "d4 - Queen's Pawn Game",
                  "c4 - English Opening",
                  "d4 d5 c4 - Queen's Gambit",
                  "d4 d5 Bf4 - Queen's Pawn Game: Accelerated London System",
                  "e4 e5 Nc3 - Vienna Game",
                  "e4 e5 f4 - King's Gambit"
                  ]
black_openings = ["e4 e5 - King's Pawn Game",
                  "e4 c5 - Sicilian Defense",
                  "e4 d5 - Scandinavian Defense",
                  "e4 e6 - French Defense",
                  "e4 c6 - Caro-Kann Defense",
                  "d4 Nf6 - Indian Defense",
                  "d4 g6 - Queen's Pawn Game: Modern Defense"
                  ]


@dataclass
class BotProfile:
    chosen_white: List[str] = field(default_factory=list)
    chosen_black: List[str] = field(default_factory=list)
    our_color: bool = True # True = White, False = Black
    opp_rating: int = 1500
    challenge_rating: int = 1500
    challenge: int = 100

    def get_openings_choice_from_user(self):
        def choose(options, color_name):
            while True:
                print(f"Select your {color_name} openings by number (comma-separated):")
                print("  0. No preference")
                for idx, opening in enumerate(options, start=1):
                    print(f"  {idx}. {opening}")
                user_input = input(f"Your {color_name} choices: ").strip()

                # default or explicit “no pref”
                # pick the "top 3" (according to me)
                # so we don't play random garbage openings with early queen out, etc.
                if user_input == "" or user_input == "0":
                    return options[:3]

                # parse comma-separated ints
                picks = []
                try:
                    picks = [int(tok) for tok in user_input.split(",") if tok.strip()]
                except ValueError:
                    print(" -> Please enter only numbers, separated by commas.")
                    continue

                # allow 0 but reject negatives or > len(options)
                if any(p < 0 or p > len(options) for p in picks):
                    print(f" -> Each number must be between 0 and {len(options)}.")
                    continue

                # any zero means no preference, so pick the "top 3" (according to me)
                # so we don't play random garbage openings with early queen out, etc.
                if 0 in picks:
                    return options[:3]

                # dedupe & map to openings
                seen = set()
                selection = []
                for p in picks:
                    if p not in seen:
                        seen.add(p)
                        selection.append(options[p - 1])
                return selection

        self.chosen_white = choose(white_openings, "White")
        self.chosen_black = choose(black_openings, "Black")
        # self.challenge = int(input(f"Relative to your ELO, what should the BOT's ELO be? ").strip())
        # new challenge-rating prompt with default = 0
        while True:
            user_input = input("Relative to your ELO, what should the BOT's ELO be? (+/- 100): ").strip()
            if user_input in ("", "0"):
                self.challenge = 0
                break
            try:
                val = int(user_input)
                self.challenge = val
                break
            except ValueError:
                print(" -> Please enter a valid integer.")
                continue

    def determine_color_and_opp_rating(self, start):
        """
        {
            'id': '4FOwDIIn',
            'variant': {'key': 'standard', 'name': 'Standard', 'short': 'Std'},
            'speed': 'rapid',
            'perf': {'name': 'Rapid'},
            'rated': False,
            'createdAt': datetime.datetime(2025, 6, 19, 22, 25, 48, 138000, tzinfo=datetime.timezone.utc),
            'white': {'id': 'wolfpacktwentythree', 'name': 'WolfpackTwentyThree', 'title': None, 'rating': 1778},
            'black': {'id': 'chess-trainer-bot', 'name': 'chess-trainer-bot', 'title': 'BOT', 'rating': 2000, 'provisional': True},
            'initialFen': 'startpos',
            'clock': {'initial': 600000, 'increment': 5000},
            'type': 'gameFull',
            'state': {'type': 'gameState', 'moves': '', 'wtime': 600000, 'btime': 600000, 'winc': 5000, 'binc': 5000, 'status': 'started'}
        }
        """
        white_player = start["white"]
        black_player = start["black"]

        # Determine our color and opponent rating
        if white_player["id"] == OUR_NAME:
            self.our_color = chess.WHITE
            self.opp_rating = black_player["rating"]
        else:
            self.our_color = chess.BLACK
            self.opp_rating = white_player["rating"]
        self.challenge_rating = self.opp_rating + self.challenge
        # return our_color, opp_rating

    @staticmethod
    def strip_opening_name(opening: str) -> str:
        if "-" not in opening:
            return opening
        return opening.split("-", 1)[1].strip()

    def get_clean_openings(self):
        return ([self.strip_opening_name(o) for o in self.chosen_white],
                [self.strip_opening_name(o) for o in self.chosen_black])

############################################### Core Bot Logic ####################################

def handle_events(bot_profile:BotProfile=BotProfile()):
    for event in client.bots.stream_incoming_events():
        t = event["type"]
        if t == "challenge":
            client.bots.accept_challenge(event["challenge"]["id"])
            print("Accepted challenge!")
        elif t == "gameStart":
            game_id = event["game"]["id"]
            print(f"Game started: {game_id}")
            play_game(game_id, bot_profile)

def make_move_on_board(board, game_id, chosen_move_uci):
    client.bots.make_move(game_id, chosen_move_uci)
    board.push_uci(chosen_move_uci)

def play_game(game_id, bot_profile: BotProfile):
    """
    Main game loop to play
    """
    # Launch engine
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    stream = client.bots.stream_game_state(game_id)

    # First message contains players’ ratings
    start = next(stream)
    bot_profile.determine_color_and_opp_rating(start)
    print("our_color, opp_rating", bot_profile.our_color, bot_profile.opp_rating)

    print(f"Playing as {'White' if bot_profile.our_color else 'Black'} vs {bot_profile.opp_rating}-rated opponent")
    bot_profile.opp_rating += bot_profile.challenge
    print(f"BOT will play at ELO: {bot_profile.opp_rating}")

    bot_profile.opp_rating = max(1320, bot_profile.opp_rating)

    # Configure Stockfish to match opponent’s strength
    engine.configure({
        "UCI_LimitStrength": True,
        "UCI_Elo": bot_profile.opp_rating
    })

    init_moves_str = start.get("state", {}).get("moves", "")
    init_moves = init_moves_str.split()
    board = chess.Board()

    print(init_moves)
    if init_moves:
        print("Moves played so far:")
        for idx, uci in enumerate(init_moves, start=1):
            color = "White" if (idx % 2) == 1 else "Black"
            print(f"  {idx}. {color}: {uci}")
            board.push_uci(uci)
    else:
        print("No moves played yet; starting from the initial position.")

    if board.turn == bot_profile.our_color:
        print("It's the BOT's turn!")
        chosen_move_uci = openings_explorer.get_book_move(board, bot_profile)
        if chosen_move_uci is None:
            engine_move = engine.play(board, limit=chess.engine.Limit(time=TIME_PER_MOVE))
            chosen_move_uci = engine_move.move.uci()
            make_move_on_board(board, game_id, chosen_move_uci)
            print(f"-> (first move from engine) {chosen_move_uci}")
        else:
            make_move_on_board(board, game_id, chosen_move_uci)
            print(f"-> (first move from openings database) {chosen_move_uci}")

    else:
        print("It's the player's turn!")

    # Main loop: respond whenever it’s our turn
    for ev in stream:
        # print("ev", ev)
        if ev.get("type") != "gameState":
            continue

        # print("board.turn", board.turn)

        # Rebuild position
        board.reset()
        for uci in ev["moves"].split():
            board.push_uci(uci)

        # Only play when it's our turn
        if board.turn == bot_profile.our_color:
            chosen_move_uci = openings_explorer.get_book_move(board, bot_profile)
            if chosen_move_uci is None:
                engine_move = engine.play(board, limit=chess.engine.Limit(time=TIME_PER_MOVE))
                if engine_move.move is None: # The game is over!
                    print("You won!")
                    break
                chosen_move_uci = engine_move.move.uci()
                make_move_on_board(board, game_id, chosen_move_uci)
                print(f"-> (from engine) {chosen_move_uci}")
            else:
                make_move_on_board(board, game_id, chosen_move_uci)
                print(f"-> (from openings database) {chosen_move_uci}")

    engine.quit()

def main() -> None:
    """Entry point for running the training bot via ``python -m``."""

    profile = BotProfile()

    try:
        profile.get_openings_choice_from_user()
    except KeyboardInterrupt:
        print("Exiting")
        return

    white, black = profile.get_clean_openings()
    print(
        "The bot will play:-\n as White -> {}\n as Black -> {}".format(
            ", ".join(white), ", ".join(black)
        )
    )

    try:
        handle_events(bot_profile=profile)
    except KeyboardInterrupt:
        print("Exiting")


if __name__ == "__main__":
    main()
