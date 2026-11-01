"""Exploit for CryptoHack's Lo-Hi Card Game.

The challenge's shuffle is not a permutation.  It serializes each LCG output
in base 52 and deals those digits in order.  The announced shuffle lengths let
us regroup the observed cards into complete LCG outputs.
"""

from __future__ import annotations

import json
import re
import socket
import sys
from dataclasses import dataclass
from typing import Any


HOST = "socket.cryptohack.org"
PORT = 13383
MODULUS = 2**61 - 1
BASE = 52
TARGET_ROUND = 200
REQUIRED_FUNDS = 130

VALUES = (
    "Ace", "Two", "Three", "Four", "Five", "Six", "Seven",
    "Eight", "Nine", "Ten", "Jack", "Queen", "King",
)
SUITS = ("Clubs", "Hearts", "Diamonds", "Spades")
CARD_INDEX = {
    f"{value} of {suit}": suit_index * len(VALUES) + value_index
    for suit_index, suit in enumerate(SUITS)
    for value_index, value in enumerate(VALUES)
}
RESHUFFLE_RE = re.compile(r"reshuffle the deck after (\d+) rounds")


class JsonSocket:
    """Newline-delimited JSON transport used by CryptoHack listeners."""

    def __init__(self, host: str, port: int) -> None:
        self.socket = socket.create_connection((host, port))
        self.reader = self.socket.makefile("r", encoding="utf-8")

    def receive(self) -> dict[str, Any]:
        line = self.reader.readline()
        if not line:
            raise ConnectionError("The challenge server closed the connection")
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError(f"Unexpected response: {response!r}")
        return response

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        self.socket.sendall((json.dumps(message) + "\n").encode())
        return self.receive()

    def close(self) -> None:
        self.reader.close()
        self.socket.close()


@dataclass
class Lcg:
    multiplier: int
    increment: int
    state: int

    def next(self) -> int:
        self.state = (
            self.state * self.multiplier + self.increment
        ) % MODULUS
        return self.state


def card_index(card: str) -> int:
    try:
        return CARD_INDEX[card]
    except KeyError as error:
        raise ValueError(f"Unknown card representation: {card!r}") from error


def base52_value(digits: list[int]) -> int:
    value = 0
    for digit in digits:
        value = value * BASE + digit
    return value


def recover_lcg(states: list[int]) -> Lcg:
    """Recover a and c from three consecutive outputs modulo the prime."""
    if len(states) < 3:
        raise ValueError("Three complete generator outputs are required")

    first, second, third = states[:3]
    denominator = (first - second) % MODULUS
    if denominator == 0:
        raise ValueError("LCG recovery encountered a non-invertible difference")
    multiplier = (
        (second - third) * pow(denominator, -1, MODULUS)
    ) % MODULUS
    increment = (second - multiplier * first) % MODULUS
    return Lcg(multiplier, increment, third)


def parse_shuffle_length(message: str) -> int | None:
    match = RESHUFFLE_RE.search(message)
    return int(match.group(1)) if match else None


def choose(hand: int, hidden: int) -> str:
    hand_rank = hand % len(VALUES)
    hidden_rank = hidden % len(VALUES)
    return "higher" if hidden_rank > hand_rank else "lower"


def best_learning_choice(hand: int) -> str:
    """Choose the more likely direction before the LCG is recovered."""
    rank = hand % len(VALUES)
    return "higher" if rank <= len(VALUES) // 2 else "lower"


def solve(host: str = HOST, port: int = PORT) -> str:
    connection = JsonSocket(host, port)
    try:
        response = connection.receive()
        observed_digits = [card_index(response["hand"])]
        current_hand = observed_digits[0]
        block_length = parse_shuffle_length(response["msg"])
        if block_length is None:
            raise ValueError("Initial response did not expose a shuffle length")

        complete_outputs: list[int] = []
        lcg: Lcg | None = None
        predicted_digits: list[int] = []

        for _ in range(1, TARGET_ROUND):
            if predicted_digits:
                hidden = predicted_digits.pop(0)
            else:
                # The hidden card is the next observed digit in the stream.
                hidden = None

            hand = current_hand
            if hidden is None:
                # The first three outputs must be learned while playing.
                # Choose the direction with the greater marginal probability.
                choice = best_learning_choice(hand)
            else:
                choice = choose(hand, hidden)

            response = connection.request({"choice": choice})
            if "error" in response:
                raise RuntimeError(response["error"])

            new_hand = card_index(response["hand"])
            current_hand = new_hand
            observed_digits.append(new_hand)
            announced_length = parse_shuffle_length(response.get("msg", ""))

            # Once a complete shuffle is observed, recover/predict the LCG.
            if block_length is not None and len(observed_digits) >= block_length:
                block = observed_digits[:block_length]
                complete_outputs.append(base52_value(block))
                observed_digits = observed_digits[block_length:]
                block_length = announced_length
                if len(complete_outputs) >= 3 and lcg is None:
                    lcg = recover_lcg(complete_outputs)
                    predicted_digits = []

            # After recovery, the next whole output can be generated exactly.
            if lcg is not None and not predicted_digits and block_length is not None:
                predicted = lcg.next()
                digits = []
                for _ in range(block_length):
                    digits.append(predicted % BASE)
                    predicted //= BASE
                predicted_digits = list(reversed(digits))

            if response["round"] == TARGET_ROUND:
                # The challenge checks the final bankroll on the following
                # request, after round 200 has been displayed.
                final = connection.request({"choice": "higher"})
                message = final.get("msg", "")
                flag_match = re.search(r"crypto\{[^}]+\}", message)
                if flag_match:
                    return flag_match.group(0)
                raise RuntimeError(
                    f"{message} (funds at round 200: {response.get('$')})"
                )

        raise RuntimeError("The challenge ended without returning a flag")
    finally:
        connection.close()


def run_until_flag(max_attempts: int = 100) -> str:
    """Retry fresh games because the unpredicted opening is probabilistic."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return solve()
        except (ConnectionError, RuntimeError, ValueError) as error:
            last_error = error
            print(f"attempt {attempt} failed: {error}", file=sys.stderr)
    raise RuntimeError(f"No flag after {max_attempts} attempts: {last_error}")


if __name__ == "__main__":
    print(run_until_flag())
