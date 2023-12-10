import num2fawords


def persian_ordinal_word(*args, **kwargs):
    res = num2fawords.ordinal_words(*args, **kwargs)
    if res == 'یکم':
        res = 'اول'
    return res


