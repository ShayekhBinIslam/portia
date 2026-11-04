"""Numbers as a narrator says them. The narration script and the ASR check share these rules, so a clip that says
"twelve point five percent" matches an ASR transcript that writes "12.5%".

  numbers_to_words("In 1979, 82% chose $2,400 for sure")
  -> "In nineteen seventy-nine, eighty-two percent chose two thousand four hundred dollars for sure"

Years 1100-1999 and 2010-2099 read as years ("nineteen seventy-nine", "twenty twenty-six"); 2000-2009 as numbers
("two thousand five"). Decimals read digit by digit ("zero point five nine"). Thousands separators must be groups of
three ("2,400"), so "1,2,3" stays a list. Not covered (write them as words in the script): ordinals, fractions,
ranges with en dashes, phone numbers, and 102 when it must not be heard as "one twenty-two" (say "a hundred and two").
"""
import re

ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def say_int(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + say_int(n % 100))
    if 1100 <= n < 2000 or 2010 <= n < 2100:  # read like a year
        lo = n % 100
        return say_int(n // 100) + (" hundred" if lo == 0 else " oh " + ONES[lo] if lo < 10 else " " + say_int(lo))
    if n < 1_000_000:
        return say_int(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + say_int(n % 1000))
    return say_int(n // 1_000_000) + " million" + ("" if n % 1_000_000 == 0 else " " + say_int(n % 1_000_000))


def say_number(s):
    """'12.5' -> 'twelve point five', '2,400' -> 'two thousand four hundred', '.5' -> 'zero point five'."""
    s = s.replace(",", "")
    if "." in s:
        whole, frac = s.split(".", 1)
        return say_int(int(whole or 0)) + " point " + " ".join(ONES[int(d)] for d in frac)
    return say_int(int(s))


def numbers_to_words(text):
    text = re.sub(r"\$(" + NUM + ")", lambda m: say_number(m.group(1)) + (" dollar" if m.group(1) == "1" else
                                                                          " dollars"), text)
    text = re.sub("(" + NUM + r")\s?%", lambda m: say_number(m.group(1)) + " percent", text)
    return re.sub(NUM, lambda m: say_number(m.group()), text)


if __name__ == "__main__":
    for t in ("In 1979, 82% chose $2,400 for sure", "12.5% of 1,000 is 125", "a 50-50 offer in 2005 and 2026",
              "0.59 against 0.61; $1 more; 1,2,3"):
        print(f"{t!r:45} -> {numbers_to_words(t)}")
