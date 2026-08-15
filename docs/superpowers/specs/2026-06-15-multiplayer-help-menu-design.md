# Multiplayer Help Menu Design

## Goal

Separate solo games from multiplayer games in Kazumi's inline help menu so users can immediately tell which commands need another player or a group.

## Menu

- Keep the existing `Games` button for solo and casino games.
- Add a new `Multiplayer` button to the main help keyboard.
- Point the group-start `Tap Race` and `Tic Tac Toe` shortcuts to the multiplayer section.

## Sections

The solo section lists Blackjack, High-Low, Word Game, Mines, Memory Match, Guess, Russian Roulette, Coinflip, casino dice, and native Telegram dice games.

The multiplayer section lists RPS, Tic Tac Toe, Connect 4, Tap Race, Word Bomb, Dice Duel, and War with concise usage instructions explaining whether users must reply to another player or play in a group.

## Verification

Automated tests verify that the new callback exists, group shortcuts open it, solo commands remain in `Games`, and multiplayer commands are absent from the solo section.
