# Computer Science Reference

Tier 1 anchor source for logic and computation.

## Boolean Logic

    AND: true only if both inputs are true.
    OR: true if at least one input is true.
    NOT: inverts the input.
    XOR: true if exactly one input is true.
    NAND and NOR are each universal — any logic circuit can be built from either alone.

De Morgan's laws:

    NOT (A AND B) = (NOT A) OR (NOT B)
    NOT (A OR B) = (NOT A) AND (NOT B)

## Binary Numbers

Each binary digit (bit) is a power of two: 1, 2, 4, 8, 16, 32, 64, 128.
Eight bits make a byte, with 256 possible values (0–255).
n bits can represent 2ⁿ distinct values.

## Algorithms

An algorithm is a finite sequence of unambiguous steps that solves a problem.
Binary search halves the search space each step: about log2(n) steps for n items.

## Information

Shannon: the information content of an event with probability p is −log2(p) bits.
A fair coin toss carries 1 bit.

## Error Detection

A parity bit makes the count of 1s even (or odd), detecting any single-bit error.
Checksums and CRCs detect corrupted data in transmission.
