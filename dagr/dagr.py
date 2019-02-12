#!/usr/bin/env python
# -*- coding: utf-8 -*-

# deviantArt Gallery Ripper
# http://lovecastle.org/dagr/
# https://github.com/voyageur/dagr

# Copying and distribution of this file, with or without
# modification, is permitted.

# This file is offered as-is, without any warranty.

import json
import re
import sys
import traceback
from email.utils import parsedate
from getopt import gnu_getopt, GetoptError
from glob import glob
from mimetypes import (
    guess_extension,
    add_type as add_mimetype,
    init as mimetypes_init
    )
from os import getcwd, makedirs, rename, utime, remove as os_remove
from os.path import (
    abspath, basename, dirname, exists as path_exists,
    expanduser, join as path_join
    )
from random import choice
from time import mktime

from bs4.element import Tag
from requests import (
    adapters as req_adapters,
    codes as req_codes,
    session as req_session
    )
from mechanicalsoup import StatefulBrowser

# Python 2/3 compatibility stuff
try:
    # Python 3
    import configparser
except ImportError:
    # Python 2
    import ConfigParser as configparser
FNF_ERROR = getattr(__builtins__, 'FileNotFoundError', IOError)


# Helper functions
def da_make_dirs(directory):
    if not path_exists(directory):
        makedirs(directory)


# Main classes
class DagrException(Exception):
    def __init__(self, value):
        super(DagrException, self).__init__(value)
        self.parameter = value

    def __str__(self):
        return str(self.parameter)


class CacheSettings():
    def __init__(self):
        self.file_names = '.filenames'
        self.downloaded_pages = '.dagr_downloaded_pages'
        self.artists = '.artists'


class Dagr:
    """deviantArt gallery ripper class"""

    NAME = basename(__file__)
    __version__ = "0.71.3"
    MAX_DEVIATIONS = 1000000  # max deviations
    ART_PATTERN = (r"https://www\.deviantart\.com/"
                   r"[a-zA-Z0-9_-]*/art/[a-zA-Z0-9_-]*")

    def __init__(self):
        # Internals
        self.init_mimetypes()
        self.browser = None
        self.errors_count = dict()

        # Configuration
        self.directory = getcwd() + "/"
        self.mature = False
        self.overwrite = False
        self.reverse = False
        self.test_only = False
        self.verbose = False
        self.save_progress = None
        self.debug = False
        self.retry_exception_names = {}
        self.cache = CacheSettings()

        # Current status
        self.deviant = ""

        self.load_configuration()

    def init_mimetypes(self):
        mimetypes_init()
        # These MIME types may be missing from some systems
        add_mimetype('image/vnd.adobe.photoshop', '.psd')
        add_mimetype('image/photoshop', '.psd')
        add_mimetype('application/rar', '.rar')
        add_mimetype('application/x-rar-compressed', '.rar')
        add_mimetype('application/x-rar', '.rar')
        add_mimetype('image/x-canon-cr2', '.tif')
        add_mimetype('application/x-7z-compressed', '.7z')
        add_mimetype('application/x-lha', '.lzh')
        add_mimetype('application/zip', '.zip')
        add_mimetype('image/x-ms-bmp', '.bmp')

    def load_configuration(self):
        my_conf = configparser.ConfigParser()
        # Try to read global then local configuration
        my_conf.read([expanduser("~/.config/dagr/dagr_settings.ini"),
                      path_join(getcwd(), "dagr_settings.ini")])
        if my_conf.has_option("DeviantArt", "MatureContent"):
            self.mature = my_conf.getboolean("DeviantArt", "MatureContent")
        if my_conf.has_option("Dagr", "OutputDirectory"):
            self.directory = abspath(
                expanduser(my_conf.get("Dagr", "OutputDirectory"))
                ) + "/"
        if my_conf.has_option("Dagr", "SaveProgress"):
            self.save_progress = my_conf.getint("Dagr", "SaveProgress")
        if my_conf.has_option("Dagr", "Verbose"):
            self.verbose = my_conf.getboolean("Dagr", "Verbose")
        if my_conf.has_option("Dagr", "Debug"):
            self.debug = my_conf.getboolean("Dagr", "Debug")
        if my_conf.has_option("Dagr.Cache", "FileNames"):
            self.cache.file_names = my_conf.get("Dagr.Cache", "FileNames")
        if my_conf.has_option("Dagr.Cache", "DownloadedPages"):
            self.cache.downloaded_pages = my_conf.get("Dagr.Cache", "DownloadedPages")
        if my_conf.has_option("Dagr.Cache", "Artists"):
            self.cache.artists = my_conf.get("Dagr.Cache", "Artists")
        if my_conf.has_option("Dagr.Cache", "IndexFile"):
            self.cache.index_file = my_conf.get("Dagr.Cache", "IndexFile")

    def start(self):
        if not self.browser:
            # Set up fake browser
            self.set_browser()

    def set_browser(self):
        user_agents = (
            'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/535.1'
            ' (KHTML, like Gecko) Chrome/14.0.835.202 Safari/535.1',
            'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:7.0.1) Gecko/20100101',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/534.50'
            ' (KHTML, like Gecko) Version/5.1 Safari/534.50',
            'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.1; Trident/4.0)',
            'Opera/9.99 (Windows NT 5.1; U; pl) Presto/9.9.9',
            'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_5_6; en-US)'
            ' AppleWebKit/530.5 (KHTML, like Gecko) Chrome/ Safari/530.5',
            'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US) AppleWebKit/533.2'
            ' (KHTML, like Gecko) Chrome/6.0',
            'Mozilla/5.0 (Windows; U; Windows NT 6.1; pl; rv:1.9.1)'
            ' Gecko/20090624 Firefox/3.5 (.NET CLR 3.5.30729)'
        )
        session = req_session()
        session.headers.update({'Referer': 'https://www.deviantart.com/'})
        if self.mature:
            session.cookies.update({'agegate_state': '1'})
        session.mount('https://', req_adapters.HTTPAdapter(max_retries=3))

        self.browser = StatefulBrowser(session=session,
                                       user_agent=choice(user_agents))


    def get_content_ext(self, url):
        if isinstance(url, Tag):
            link = self.browser.find_link(url)
            url = self.absolute_url(link['href'])
        head_resp = self.browser.session.head(url)
        if head_resp.headers.get("content-type"):
            return next(iter(head_resp.headers.get("content-type").split(";")), None)


    def get(self, url, file_name=None, files_list=None):
        if file_name and files_list == None:
            raise ValueError('files_list cannot be empty when file_name is specified')
        if (file_name and not self.overwrite):
            glob_name = next((fn for fn in files_list if file_name in fn), None)
            if glob_name:
                print(glob_name, "exists - skipping")
                return None

        new_name = None

        if file_name:
            content_type = self.get_content_ext(url)
            if content_type:
                file_ext = guess_extension(content_type)
                if file_ext:
                    new_name = file_name + file_ext
                    file_exists = path_exists(new_name)
                else:
                    raise DagrException('unknown content-type - ' + content_type)

            if file_exists and not self.overwrite:
                files_list.append(new_name)
                return None

        get_resp = None
        tries = {}
        while True:
            try:
                if isinstance(url, Tag):
                    # Download and save soup links
                    get_resp = self.browser.download_link(url, file_name)
                else:
                    # Direct URL
                    get_resp = self.browser.session.get(url)
                    if file_name:
                        with open(file_name, "wb") as local_file:
                            local_file.write(get_resp.content)
                break
            except Exception as ex:
                if self.verbose:
                    traceback.print_exc()
                except_name = type(ex).__name__
                if except_name in self.retry_exception_names:
                    if not except_name in tries:
                        tries[except_name] = 0
                    tries[except_name] += 1
                    if tries[except_name]  < 3:
                        continue
                    raise DagrException('Failed to get url: {}'.format(except_name))
                else:
                    raise ex

        if get_resp.status_code != req_codes.ok:
            raise DagrException("incorrect status code - " +
                                str(get_resp.status_code))

        if file_name is None:
            return get_resp.text

        if get_resp.headers.get("last-modified"):
            # Set file dates to last modified time
            mod_time = mktime(parsedate(get_resp.headers.get("last-modified")))
            utime(file_name, (mod_time, mod_time))

            if new_name:
                if file_exists and self.overwrite:
                    os_remove(new_name)
                rename(file_name, new_name)

        files_list.append(new_name)
        return new_name

    def find_link(self, link):
        filelink = None
        filename = basename(link)
        mature_error = False
        self.browser.open(link)
        # Full image link (via download link)
        link_text = re.compile("Download( (Image|File))?")
        img_link = None
        for candidate in self.browser.links("a"):
            if link_text.search(candidate.text) and candidate.get("href"):
                img_link = candidate
                break

        if img_link and img_link.get("data-download_url"):
            return (filename, img_link)

        if self.verbose:
            print("Download link not found, falling back to direct image")

        current_page = self.browser.get_current_page()
        # Fallback 1: try meta (filtering blocked meta)
        filesearch = current_page.find("meta", {"property": "og:image"})
        if filesearch:
            filelink = filesearch['content']
            if basename(filelink).startswith("noentrythumb-"):
                filelink = None
                mature_error = True
        if not filelink:
            # Fallback 2: try collect_rid, full
            filesearch = current_page.find("img",
                                           {"collect_rid": True,
                                            "class": re.compile(".*full")})
            if not filesearch:
                # Fallback 3: try collect_rid, normal
                filesearch = current_page.find("img",
                                               {"collect_rid": True,
                                                "class":
                                                    re.compile(".*normal")})
            if filesearch:
                filelink = filesearch['src']

        page_title = current_page.find("span", {"itemprop": "title"})
        if page_title and page_title.text == "Literature":
            filelink = self.browser.get_url()
            return (filename, filelink)

        if not filelink:
           filelink = self.find_video(current_page)

        if not filelink:
            iframe_search = current_page.find('iframe', {'class': 'flashtime'})
            if iframe_search:
                self.browser.open(iframe_search.attrs['src'])
                current_page = self.browser.get_current_page()
                embed_search = current_page.find('embed', {'id': 'sandboxembed'})
                if embed_search:
                    filelink = embed_search.attrs['src']

        if not filelink:
            if mature_error:
                if self.mature:
                    raise DagrException("maybe not an image")
                else:
                    raise DagrException("maybe a mature deviation/" +
                                        "not an image")
            else:
                raise DagrException("all attemps to find a link failed")

        return (filename, filelink)

    def find_video(self, current_page):
        try:
            script = self.filter_page_scripts(current_page, 'deviantART.pageData=')
            best_res = self.extract_nested_assign(script,['deviantART.pageData', '"film"', '"sizes"'])[-1]
            return json.loads(str(self.extract_nested_assign(best_res, ['"src"'])))
        except (ImportError, StopIteration):
            pass

    def filter_page_scripts(self, current_page, filt):
        return next(content for content in
                    (script.get_text() for script in
                            current_page.find_all('script', {'type':'text/javascript'})
                        if not script.has_attr('src'))
                    if content and filt in content)

    def extract_nested_assign(self, node, identifiers):
        from calmjs.parse import es5 as calmjs_es5
        from calmjs.parse.asttypes import (
            Node as calmjs_node,
            Assign as calmjs_assign,
            Object as calmjs_obj
            )
        from calmjs.parse.walkers import Walker as calmjs_walker
        if not isinstance(node, calmjs_node):
            node  = calmjs_es5(node)
        walker = calmjs_walker()
        def calmjs_do_extract(node, identifiers):
            identifier = identifiers.pop(0)
            sub_node = next(walker.filter(node, lambda n: (
                isinstance(n, calmjs_assign) and
                str(n.left) == identifier)))
            if identifiers:
                return self.extract_nested_assign(sub_node, identifiers)
            if isinstance(sub_node.right, calmjs_obj):
                return list(sub_node.right)
            return sub_node.right
        return calmjs_do_extract(node, identifiers)

    def handle_download_error(self, link, link_error):
        error_string = str(link_error)
        print("Download error (" + link + ") : " + error_string)
        if error_string in self.errors_count:
            self.errors_count[error_string] += 1
        else:
            self.errors_count[error_string] = 1

    def get_pages(self, mode, base_url):
        pages = []
        for i in range(0, int(Dagr.MAX_DEVIATIONS / 24), 24):
            html = ""
            url = base_url + str(i)

            try:
                html = self.get(url)
            except DagrException:
                print("Could not find " + self.deviant + "'s " + mode)
                return pages

            prelim = re.findall(Dagr.ART_PATTERN, html,
                                re.IGNORECASE | re.DOTALL)

            for match in prelim:
                if match not in pages:
                    pages.append(match)

            done = re.findall("(This section has no deviations yet!|"
                              "This collection has no items yet!|"
                              "Sorry, we found no relevant results.|"
                              "Sorry, we don't have that many results.)",
                              html, re.IGNORECASE | re.S)

            if done:
                break

            progress_msg = '{} page {} crawled...'.format(mode, int(i / 24) + 1)
            if mode == 'search':
                print(progress_msg)
            else:
                print("{}'s {}". format(self.deviant, progress_msg))

        if not self.reverse:
            pages.reverse()

        return pages

    def load_cache_file(self, base_dir, cache_file):
        full_path = path_join(base_dir, cache_file)
        try:
            if path_exists(full_path):
                with open(full_path, 'r') as filehandle:
                    return json.load(filehandle)
            else:
                if self.verbose:
                    print('Primary {} cache not found'.format(cache_file))
        except:
            print('Unable to load primary {} cache:'.format(cache_file))
            traceback.print_exc()
        full_path += '.bak'
        try:
            if path_exists(full_path):
                with open(full_path, 'r') as filehandle:
                    return json.load(filehandle)
            else:
                if self.verbose:
                    print('Backup {} cache not found'.format(cache_file))
        except:
            print('Unable to load backup {} cache:'.format(cache_file))
            traceback.print_exc()

    def load_cache(self, base_dir, **kwargs):
        def filenames():
            if self.verbose:
                print('Building filenames cache')
            files_list_raw = glob(path_join(base_dir, '*'))
            return [basename(fn) for fn in files_list_raw]
        def downloaded_pages():
            return []
        def artists():
            return {}
        cache_defaults = {
            'filenames': filenames,
            'downloaded_pages': downloaded_pages,
            'artists': artists
        }
        for cache_type, cache_file in kwargs.items():
            cache_contents = self.load_cache_file(base_dir, cache_file)
            if cache_contents:
                yield cache_contents
            else:
                if not cache_type in cache_defaults:
                    raise ValueError('Unkown cache type: {}'.format(cache_type))
                yield cache_defaults[cache_type]()

    def get_images(self, mode, mode_arg, pages):
        if mode == 'search':
            base_dir =  path_join(self.directory, mode)
        else:
            base_dir = path_join(self.directory, self.deviant, mode)
        if mode_arg:
            base_dir = path_join(base_dir, mode_arg)
        try:
            da_make_dirs(base_dir)
        except OSError as mkdir_error:
            print(str(mkdir_error))
            return
        #Load caches
        fn_cache =  self.cache.file_names
        dp_cache = self.cache.downloaded_pages
        files_list, existing_pages = self.load_cache(base_dir,
            filenames = fn_cache,
            downloaded_pages = dp_cache
        )
        if not self.overwrite:
            pages = [x for x in pages if x not in existing_pages]
        print("Total deviations to download: " + str(len(pages)))
        for count, link in enumerate(pages, start=1):
            if self.save_progress and count % self.save_progress == 0:
                self.update_downloaded_pages(base_dir, existing_pages)
                self.update_filenames(base_dir, files_list)
            if self.verbose:
                print("Downloading " + str(count) + " of " +
                      str(len(pages)) + " ( " + link + " )")
            filename = ""
            filelink = ""
            try:
                filename, filelink = self.find_link(link)
            except (KeyboardInterrupt, SystemExit):
                raise
            except DagrException as link_error:
                self.handle_download_error(link, link_error)
                continue
            if not self.test_only:
                try:
                    self.get(filelink, path_join(base_dir, filename), files_list)
                except DagrException as get_error:
                    self.handle_download_error(link, get_error)
                    continue
                else:
                    if link not in existing_pages:
                        existing_pages.append(link)
            else:
                print(filelink)
        if pages or (not path_exists(path_join(base_dir, self.cache.file_names)) and files_list):
            self.filenames_path(base_dir,self.cache.file_names, files_list)
        if pages:
            self.update_downloaded_pages(base_dir, existing_pages)
        if pages or (
                not path_exists(path_join(base_dir, self.cache.artists))
                and existing_pages):
            self.update_artists(base_dir, existing_pages, files_list)

    def backup_cache_file(file_name):
        backup_name = file_name + '.bak'
        if path_exists(file_name):
            if path_exists(backup_name):
                os_remove(backup_name)
            rename(file_name, backup_name)

    def update_cache(self, base_dir, cache_file, cache_contents):
        full_path = path_join(base_dir, cache_file)
        self.backup_cache_file(full_path)
        if self.verbose:
            print('Updating {} cache'.format(cache_file))
        with open(full_path, 'w') as filehandle:
            json.dump(cache_contents, filehandle, indent=4, sort_keys=True)

    def update_artists(self, base_dir, pages, files_list):
        artists = {}
        for page in pages:
            artist_url = dirname(dirname(page))
            artist_name = basename(artist_url)
            url_basename = basename(page)
            real_filename = next(fn for fn in files_list if url_basename in fn)
            if not artist_name in artists:
                artists[artist_name] = {'Home Page': artist_url, 'Artworks':{}}
            artists[artist_name]['Artworks'][real_filename] = page
        self.update_cache(base_dir, self.cache.artists, artists)

    def global_search(self, query):
        base_url = 'https://www.deviantart.com/?q=' + query  + '&offset='
        pages = self.get_pages('search', base_url)
        if not pages:
            print('No search results for query {}'.format(query))
            return
        print('Total search results found for {} : {}'.format(query, len(pages)))
        self.get_images('search', query, pages)
        print('Query successfully ripped.')

    def deviant_get(self, mode, mode_arg=None):
        print("Ripping " + self.deviant + "'s " + mode + "...")

        base_url = "https://www.deviantart.com/" + self.deviant.lower() + "/"

        if mode == "favs":
            base_url += "favourites/?catpath=/&offset="
        elif mode == "collection":
            base_url += "favourites/" + mode_arg + "?offset="
        elif mode == "scraps":
            base_url += "gallery/?catpath=scraps&offset="
        elif mode == "gallery":
            base_url += "gallery/?catpath=/&offset="
        elif mode == "album":
            base_url += "gallery/" + mode_arg + "?offset="
        elif mode == "query":
            base_url += "gallery/?q=" + mode_arg + "&offset="
        elif mode == "category":
            base_url += "gallery/?catpath=" + mode_arg + "&offset="

        pages = self.get_pages(mode, base_url)
        if not pages:
            print(self.deviant + "'s " + mode + " had no deviations.")
            return
        print("Total deviations in " + self.deviant + "'s " +
              mode + " found: " + str(len(pages)))

        self.get_images(mode, mode_arg, pages)

        print(self.deviant + "'s " + mode + " successfully ripped.")

    def group_get(self, mode):
        print("Ripping " + self.deviant + "'s " + mode + "...")

        base_url = 'https://www.deviantart.com/' + self.deviant.lower() + '/'
        if mode == "favs":
            base_url += "favourites/"
        elif mode == "gallery":
            base_url += "gallery/"

        folders = []

        i = 0
        while True:
            html = self.get(base_url + '?offset=' + str(i))
            k = re.findall('class="ch-top" href="' + base_url +
                           '([0-9]*/[a-zA-Z0-9_-]*)"',
                           html, re.IGNORECASE)
            if k == []:
                break

            new_folder = False
            for match in k:
                if match not in folders:
                    folders.append(match)
                    new_folder = True
            if not new_folder:
                break
            i += 10

        # no repeats
        folders = list(set(folders))

        if not folders:
            print(self.deviant + "'s " + mode + " is empty.")

        print("Total folders in " + self.deviant + "'s " +
              mode + " found: " + str(len(folders)))

        if self.reverse:
            folders.reverse()

        pages = []
        for folder in folders:
            label = folder.split("/")[-1]
            print("Crawling folder " + label + "...")
            pages = self.get_pages(mode, base_url + folder + '?offset=')

            if not self.reverse:
                pages.reverse()

            self.get_images(mode, label, pages)

        print(self.deviant + "'s " + mode + " successfully ripped.")

    def print_errors(self):
        if self.errors_count:
            print("Download errors count:")
            for error in self.errors_count:
                print("* " + error + " : " + str(self.errors_count[error]))


def print_help():
    print(Dagr.NAME + " v" + Dagr.__version__ + " - deviantArt gallery ripper")
    print("Usage: " + Dagr.NAME +
          " [-d directory] " + "[-fgmhorstv] " +
          "[-q query_text] [-c collection_id/collection_name] " +
          "[-a album_id/album_name] " +
          "[-k category] " +
          "deviant1 [deviant2] [...]")
    print("Example: " + Dagr.NAME + " -gsfv derp123 blah55")
    print("For extended help and other options, run " + Dagr.NAME + " -h")


def print_help_detailed():
    print_help()
    print("""
Argument list:
-d, --directory=PATH
directory to save images to, default is current one
-m, --mature
allows to download mature content
-g, --gallery
downloads entire gallery
-s, --scraps
downloads entire scraps gallery
-f, --favs
downloads all favourites
-c, --collection=NUMERIC_ID/NAME
downloads specified favourites collection
 You need to specify both id and name (from the collection URL)
 Example: 123456789/my_favourites
-a, --album=NUMERIC_ID/NAME
downloads specified album
 You need to specify both id and name (from the album URL)
 Example: 123456789/my_first_album
-q, --query=QUERY_TEXT
downloads artwork matching specified query string
-k, --category=CATEGORY
downloads artwork matching a category (value in catpath in URL)
-t, --test
skips the actual downloads, just prints URLs
-h, --help
prints help and exits (this text)
-r, --reverse
download oldest deviations first
-o, --overwrite
redownloads a file even if it already exists
-v, --verbose
outputs detailed information on downloads
-p, --progress=COUNT
save image cache after every COUNT downloads

Proxies:
 you can also configure proxies by setting the environment variables
 HTTP_PROXY and HTTPS_PROXY

$ export HTTP_PROXY="http://10.10.1.10:3128"
$ export HTTPS_PROXY="http://10.10.1.10:1080"
""")

def get_deviant(ripper, deviant_name):
    group = False
    html = ripper.get('https://www.deviantart.com/' + deviant_name + '/')
    deviant = re.search(r'<title>.[A-Za-z0-9-]*', html,
                        re.IGNORECASE).group(0)[7:]
    deviant = re.sub('[^a-zA-Z0-9_-]+', '', deviant)
    if re.search('<dt class="f h">Group</dt>', html):
        group = True
    return deviant, group

def main():
    gallery = scraps = favs = False
    collection = album = query = category = ""

    if len(sys.argv) <= 1:
        print_help()
        sys.exit()

    g_opts = "d:mu:p:a:q:k:p:c:vfgshrto"
    g_long_opts = ['directory=', 'mature',
                    'album=', 'query=', 'collection=',
                    'verbose', 'favs', 'gallery', 'scraps',
                    'help', 'reverse', 'test', 'overwrite',
                    'category', 'progress']
    try:
        options, deviants = gnu_getopt(sys.argv[1:], g_opts, g_long_opts)
    except GetoptError as err:
        print("Options error: " + str(err))
        sys.exit()

    ripper = Dagr()

    for opt, arg in options:
        if opt in ('-h', '--help'):
            print_help_detailed()
            sys.exit()
        elif opt in ('-d', '--directory'):
            ripper.directory = abspath(expanduser(arg)) + "/"
        elif opt in ('-m', '--mature'):
            ripper.mature = True
        elif opt in ('-s', '--scraps'):
            scraps = True
        elif opt in ('-g', '--gallery'):
            gallery = True
        elif opt in ('-r', '--reverse'):
            ripper.reverse = True
        elif opt in ('-f', '--favs'):
            favs = True
        elif opt in ('-c', '--collection'):
            collection = arg.strip().strip('"')
        elif opt in ('-v', '--verbose'):
            ripper.verbose = True
        elif opt in ('-a', '--album'):
            album = arg.strip()
        elif opt in ('-q', '--query'):
            query = arg.strip().strip('"')
        elif opt in ('-k', '--category'):
            category = arg.strip().strip('"')
        elif opt in ('-t', '--test'):
            ripper.test_only = True
        elif opt in ('-o', '--overwrite'):
            ripper.overwrite = True
        elif opt in ('-p', '--progress'):
            if arg:
                ripper.save_progress = int(arg)

    run_ripper(ripper, deviants, gallery, scraps, favs, collection, album, query, category)
    ripper.print_errors()


def run_ripper(ripper, deviants, galleries=False, scraps=False, favs=False, collections=None, albums=None, queries=None, categories=None):
    print(Dagr.NAME + " v" + Dagr.__version__ + " - deviantArt gallery ripper")
    if deviants == []:
        print("No deviants entered. Exiting.")
        sys.exit()
    if not any([galleries, scraps, favs, collections, albums, queries, categories]):
        print("Nothing to do. Exiting.")
        sys.exit()

    # Only start when needed
    ripper.start()

    for deviant in deviants:
        try:
            deviant, group = get_deviant(ripper, deviant)
        except DagrException:
            print("Deviant " + deviant + " not found or deactivated!")
            continue
        if group:
            print("Current group: " + deviant)
        else:
            print("Current deviant: " + deviant)
        try:
            da_make_dirs(ripper.directory + deviant)
        except OSError as mkdir_error:
            print(str(mkdir_error))

        ripper.deviant = deviant
        if group:
            if galleries:
                ripper.group_get("gallery")
            if favs:
                ripper.group_get("favs")
            if any([scraps, collections, albums, queries]):
                print("Unsupported modes for groups were ignored")
        else:
            if galleries:
                ripper.deviant_get("gallery")
            if scraps:
                ripper.deviant_get("scraps")
            if favs:
                ripper.deviant_get("favs")
            if collections:
                if isinstance(collections, str):
                    collections = [collections]
                for collection in collections:
                    ripper.deviant_get("collection", mode_arg=collection)
            if albums:
                if isinstance(albums, str):
                    albums = [albums]
                for album in albums:
                    ripper.deviant_get("album", mode_arg=album)
            if queries:
                if isinstance(queries, str):
                    queries = [queries]
                for query in queries:
                    ripper.deviant_get("query", mode_arg=query)
            if categories:
                if isinstance(categories, str):
                    categories = [categories]
                for category in categories:
                    ripper.deviant_get("category", mode_arg=category)
    print("Job complete.")


if __name__ == "__main__":
    main()

# vim: set tabstop=4 softtabstop=4 shiftwidth=4 expandtab:
