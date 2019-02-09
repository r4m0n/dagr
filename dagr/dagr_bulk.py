import dagr, json, traceback
from dagr import run_ripper, add_mimetype

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
        self.searches = []
        with open('dagr_bulk.json', 'r') as filehandle:
            self.__dict__.update(json.load(filehandle))

def main():
    add_mimetype('binary/octet-stream', '.bin')
    config = DagrBulkConfig()
    ripper = dagr.Dagr()
    ripper.retry_exception_names = ['OSError', 'ChunkedEncodingError']
    for query in config.searches:
        ripper.start()
        ripper.global_search(query)
    for deviant, albums in config.albums.items():
        run_ripper(ripper, [deviant], albums=albums)
    if config.galleries:
        run_ripper(ripper, config.galleries, galleries=True)
    if config.scraps:
        run_ripper(ripper, config.scraps, scraps=True)
    for deviant, collections in config.collections.items():
       run_ripper(ripper, [deviant], collections=collections)
    for deviant, queries in config.queries.items():
        run_ripper(ripper, [deviant], queries=queries)
    for deviant, category in config.categories.items():
        run_ripper(ripper, [deviant], categories=category)
    if config.favs:
        run_ripper(ripper, config.favs, favs=True)
    ripper.print_errors()



if __name__ == '__main__':
    main()