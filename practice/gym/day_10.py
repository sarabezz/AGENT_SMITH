
# idea: a set where we have the items we've seen, a result list to save the chars.
def remove_duplicates(items):
    seen = set()
    result = []
    for c in items:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# idea:
def word_lengths(text):
    result = {}
    for word in text.split():
        result[word] = len(word)
    return result


# idea:
def merge_counts(a, b):
    result = dict(a)
    for k, v in b.items():
        if k in result: # if k in result
            result[k] = result[k] + v # then its value is its result value plus v
        else: # if not
            result[k] = v # just add v to k in result
    return result

def merge_counts(a, b):
    result = dict(a)
    for k, v in b.items():
        result[k] = result.get(k, 0) + v # if not k in result 0 + v
    return result

