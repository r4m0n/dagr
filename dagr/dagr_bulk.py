import dagr, json, traceback
from dagr import run_ripper

class DagrBulkConfig():
    def __init__(self):
        self.output_dir = ""
        self.albums = {}
        self.collections = {}
        self.queries = {}
        self.favs = []
        self.galleries = []
        self.scraps = []
        self.categories = {}
        with open('dagr_bulk.json', 'r') as filehandle:
            self.__dict__.update(json.load(filehandle))

def main():
    config = DagrBulkConfig()
    ripper = dagr.Dagr()
    ripper.retry_exception_names = ['OSError', 'ChunkedEncodingError']
    for deviant, albums in config.albums.items():
        run_ripper(ripper, [deviant], albums=albums)
    for deviant, collections in config.collections.items():
       run_ripper(ripper, [deviant], collections=collections)
    for deviant, queries in config.queries.items():
        run_ripper(ripper, [deviant], queries=queries)
    for deviant, category in config.categories.items():
        run_ripper(ripper, [deviant], categories=category)
    if config.galleries:
        run_ripper(ripper, config.galleries, galleries=True)
    if config.scraps:
        run_ripper(ripper, config.scraps, scraps=True)
    if config.favs:
        run_ripper(ripper, config.favs, favs=True)
    ripper.print_errors()



if __name__ == '__main__':
    main()