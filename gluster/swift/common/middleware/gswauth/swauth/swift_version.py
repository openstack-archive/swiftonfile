import swift


MAJOR = None
MINOR = None
REVISION = None
FINAL = None


def parse(value):
    parts = value.split('.')
    if parts[-1].endswith('-dev'):
        final = False
        parts[-1] = parts[-1][:-4]
    else:
        final = True
    major = int(parts.pop(0))
    minor = int(parts.pop(0))
    if parts:
        revision = int(parts.pop(0))
    else:
        revision = 0
    return major, minor, revision, final


def newer_than(value):
    global MAJOR, MINOR, REVISION, FINAL
    major, minor, revision, final = parse(value)
    if MAJOR is None:
        MAJOR, MINOR, REVISION, FINAL = parse(swift.__version__)
    if MAJOR < major:
        return False
    elif MAJOR == major:
        if MINOR < minor:
            return False
        elif MINOR == minor:
            if REVISION < revision:
                return False
            elif REVISION == revision:
                if not FINAL or final:
                    return False
    return True


def run_tests():
    global MAJOR, MINOR, REVISION, FINAL
    MAJOR, MINOR, REVISION, FINAL = parse('1.3')
    assert(newer_than('1.2'))
    assert(newer_than('1.2.9'))
    assert(newer_than('1.3-dev'))
    assert(newer_than('1.3.0-dev'))
    assert(not newer_than('1.3'))
    assert(not newer_than('1.3.0'))
    assert(not newer_than('1.3.1-dev'))
    assert(not newer_than('1.3.1'))
    assert(not newer_than('1.4'))
    assert(not newer_than('2.0'))
    MAJOR, MINOR, REVISION, FINAL = parse('1.7.7-dev')
    assert(newer_than('1.6'))
    assert(newer_than('1.7'))
    assert(newer_than('1.7.6-dev'))
    assert(newer_than('1.7.6'))
    assert(not newer_than('1.7.7'))
    assert(not newer_than('1.7.8-dev'))
    assert(not newer_than('1.7.8'))
    assert(not newer_than('1.8.0'))
    assert(not newer_than('2.0'))


if __name__ == '__main__':
    run_tests()
