# Lo-Hi Card Game (CryptoHack) - Write-up & Solution

This repository contains my Python solution for the **Lo-Hi Card Game** challenge on CryptoHack (Misc category). 

> **Note:** In accordance with CryptoHack's rules, the final flag has been redacted from the code and this write-up.

## Challenge Description
The challenge simulates a casino card game where the player must guess if the next card drawn will be higher or lower than their current card. The casino uses a homemade pseudo-random number generator (PRNG) to shuffle the deck. The goal is to exploit the PRNG, predict the cards, and win enough money to purchase the flag.

## The Vulnerability
The casino's PRNG is a Linear Congruential Generator (LCG) with a modulus of \(2^{61}-1\). The critical flaw is that the LCG parameters (multiplier and increment) are generated once at the start of the game and remain constant. 

Additionally, the deck is not truly "shuffled." The server generates a large LCG output and converts it into a base-52 number to represent the order of the cards.

Because the LCG is linear, observing just **three complete outputs** of the generator allows us to solve for the multiplier and increment. Once we have those, we can predict every future card the server will deal.

## Exploit Strategy
The `solve.py` script automates the heist in three phases:

1. **The Learning Phase:** We play the game blindly for the first few rounds. We use a safe heuristic: guess "Higher" if our card is low (e.g., below 7) and "Lower" if our card is high. This keeps our funds alive while we gather data.
2. **State Recovery:** The server announces the shuffle block length. We group the observed cards into these blocks, convert them from base-52 to integers, and collect three full outputs.
3. **The Heist Phase:** We calculate the LCG multiplier and increment using algebraic equations. We then generate the exact sequence of future cards locally, send perfect guesses to the server for every round, and win the required $130.

## How to Run
1. Ensure you have the required libraries installed:
   ```bash
   pip install pwntools