from client.core.game import Game
from client.core.player_identity import parse_slot_from_argv

if __name__ == "__main__":
    g = Game(slot=parse_slot_from_argv())
    g.run()
