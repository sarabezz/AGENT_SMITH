
# idea: go through the lists inside the list, then inside the items inside every list and add them to the final list
def flatten(lists):
    result = []
    for inner in lists:
        for item in inner:
            result.append(item)
    return result

def flatten(lists):
    return (item for inner in lists for item in inner)


# idea: take the first and add it the rest ones, if doesn't give target, try with the second one
def find_pair_sum(numbers, target):
    i = 0
    j = 0
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if numbers[i] + numbers[j] == target:
                return numbers[i], numbers[j]
            j += 1
        i += 1
    return None

def find_pair_sum(numbers, target):
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if numbers[i] + numbers[j] == target:
                return (numbers[i], numbers[j])
    return None

# idea: for each number, compute the partner it needs (target - number);
#       if I've already seen that partner, I found the pair
def find_pair_sum(numbers, target):
    seen = set()
    for n in numbers:
        partner = target - n
        if partner in seen:
            return (partner, n)
        seen.add(n)
    return None


# idea: create an empty dict, go through the given one, take its values and keys and add them to the dict swapped (or the other wahy around)
def invert_dict(d):
    result = {}
    for k, v in d.items():
        result[v] = k
    return result

def inver_dict(d):
    return {v: k for k, v in d.items()}