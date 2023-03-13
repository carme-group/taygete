from . import configure

if __name__ != "__main__":
    raise ImportError("module is not for importing", __name__)

configure.main()
