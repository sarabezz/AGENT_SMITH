
# idea: create a dict with the 3 keys and their values 0, go through the text and if the char is one of them add 1 its value
def count_char_types(text):
    result = {
        "letters": 0,
        "digits": 0,
        "spaces": 0
        }
    # keys = ["letters", "digits", "spaces"]
    # result = dict.fromkeys(keys, 0)
    for char in text:
        if char.isalpha():
            result["letters"] += 1
        elif char.isdigit():
            result["digits"] += 1
        elif char.isspace():
            result["spaces"] += 1
    return result

def count_char_types(text):
    return {
        "letters": sum(c.isalpha() for c in text),
        "digits": sum(c.isdigit() for c in text),
        "spaces": sum(c.isspace() for c in text),
    }
    # The trick: in Python, True counts as 1 and False as 0. So sum(...) of the Trues = how many there are:
    # sum([True, False, True])    # 2
    """Honest trade-off: this version walks the text 3 times (once per key), while yours walks it once. For huge texts, yours is faster. Both are good answers; this one is just shorter to read."""


# idea: 
def is_balanced(text):
    count = 0
    for char in text:
        if char == "(":
            count += 1
        elif char == ")":
            count -= 1
            if count == -1:
                return False
    return count == 0


# idea:
def running_sum(numbers):
    total = 0
    result = []
    for n in numbers:
        total += n
        result.append(total)
    return result

from itertools import accumulate
def running_sum(numbers):
    return list(accumulate(numbers))

    
