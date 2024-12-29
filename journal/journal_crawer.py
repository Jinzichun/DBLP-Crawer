import requests
from bs4 import BeautifulSoup
import re
import csv
import logging
import argparse
import os

# Argument parsing
parser = argparse.ArgumentParser(description='DBLP journal crawler.')
parser.add_argument('--syear', type=int, default=2020, metavar="INT", 
                    help='Year to start the crawler. Default: 2020')
parser.add_argument("--sthreshod", type=float, default=0.4, metavar="FLOAT", 
                    help="Threshold for the paper score to add to the paper list. Default: 0.4")
parser.add_argument("--filename", default="journal.csv", metavar="*.csv", 
                    help="Filename to save the papers. Default: journal_data.csv")
parser.add_argument("--strictmatch", type=bool, default=False, 
                    help="Enable strict match, default: False")
parser.add_argument("--journal", default=None, 
                    help="Specify target journal.")
parser.add_argument("--loglevel", choices=["debug", "info", "silent"], default="info", 
                    help="Logging level. Default: info")
parser.add_argument("--logfilename", default="journal-dblplog.log")
args = parser.parse_args()

# Logging setup
logmap = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "silent": logging.CRITICAL
}
logger = logging.getLogger("dblp journal crawler log")
logger.setLevel(logmap[args.loglevel])
ch = logging.FileHandler(args.logfilename, "w")
ch.setLevel(logmap[args.loglevel])
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
sh = logging.StreamHandler()
sh.setLevel(logmap[args.loglevel])
sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ch)
logger.addHandler(sh)

keywords = {
    "linear": 0.2,
    "attention": 0.2,
}

venue_set = {
    "journal": ["tocs", "tos", "tcad", "tc", "tpds", "taco", "taas", "todaes", "tecs", "trets", "tvlsi", "jpdc", "jsa", "parco", "jsac", "tmc", "ton", "toit", "tomccap", "tosn", "cn", "tcom", "twc", "tdsc", "tifs",  "tissec", "jcs", "toplas", "tosem", "tse", "tsc", "ase", "ese", "iets", "ist", "jfp", "jss", "re", "scp", "sosym", "stvr", "spe", "tods", "tois", "tkde", "vldbj", "tkdd", "tweb", "aei", "dke", "dmkd", "ejis", "ipm", "is", "jasist", "jws", "kais", "tit", "iandc", "sicomp", "talg", "tocl", "toms", "algorithmica", "cc", "fac", "fmsd", "informs", "jcss", "jgo", "jsc", "mscs", "tcs", "tog", "tip", "tvcg", "tomccap", "cagd", "cgf", "cad", "gm", "tcsvt", "tmm", "jasa", "siims", "speech com", "ai", "tpami", "ijcv", "jmlr", "tap", "aamas", "cviu", "dke", "tac", "taslp", "tec", "tfs", "tnnls", "ijar", "jair", "jslhr", "pr", "tacl", "tochi", "ijhcs", "cscw", "hci", "iwc", "ijhci", "umuai", "tsmc", "jacm", "proc. ieee", "scis", "cognition", "tasae", "tgars", "tits", "tmi", "tr", "tcbb", "jcst", "jamia", "www"]
}
YEAR_START = args.syear
SCORE_THRESHOD = args.sthreshod

# Paper class
class Paper:
    def __init__(self, title=None, journal=None, year=None, pages=None, bibtex_url=None):
        self.title = title
        self.journal = journal
        self.year = year
        self.pages = pages
        self.authors = []
        self.score = None
        self.bibtex_url = bibtex_url

    def calScore(self):
        self.score = sum(keywords[keyword] for keyword in keywords if keyword in self.title.lower())

    def __str__(self):
        return "{} {}, {} {}, BibTeX URL: {}".format(
            self.title, self.pages, self.journal, self.year, self.bibtex_url
        )

# Save papers to CSV file without the score column
def savePaper2csv(paper_list, filename):
    with open(f"{filename}", "w") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "journal", "year", "pages", "authors", "bibtex_url"])
        for paper in paper_list:
            writer.writerow([paper.title, paper.journal, paper.year, paper.pages, ", ".join(paper.authors), paper.bibtex_url])

# Extract content strings from HTML tag
def getContentStrings(tag):
    return "".join([getContentStrings(c) if hasattr(c, 'contents') else c.string for c in tag.contents])

# Search for papers in a specific journal
def searchJournal(journal, keywords, filename):
    dblp_url = "https://dblp.org/search/publ/inc"
    journalre = re.compile(".*{}.*".format(journal), re.IGNORECASE)
    if args.strictmatch:
        journalre = re.compile("(?=^((?!workshop).)*$)(?=[^@]?{}[^@]?)".format(journal), re.IGNORECASE)
    search_word = "|".join(keywords) + f" streamid:journals/{journal}:"

    page = 0
    year_smaller_bool = False
    paper_list = []
    max_pages = 50  # Set maximum number of pages to search

    if not os.path.exists(filename):
        savePaper2csv([], filename)  # Ensure file exists with header

    while not year_smaller_bool and page < max_pages:
        payload = {
            "q": search_word,
            "s": "ydvspc",
            "h": "1000",
            "b": f"{page}",
        }

        try:
            r = requests.get(dblp_url, params=payload, timeout=10)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        record_list = soup.find_all("li", class_=re.compile("year|article"))

        if not record_list:
            logger.warning("No more papers can be found!")
            break

        for record in record_list:
            if "year" in record["class"]:
                try:
                    year = int(record.string)
                    if year < YEAR_START:
                        year_smaller_bool = True
                        break
                except (ValueError, TypeError):
                    continue
            elif "article" in record["class"]:
                authors = record.cite.find_all(itemprop="author")
                title_tag = record.cite.find(class_="title")
                paper_title = getContentStrings(title_tag)
                paper_journal = record.cite.find(itemprop="isPartOf").string
                pagination_tag = record.cite.find(itemprop="pagination")
                paper_pagination = pagination_tag.string if pagination_tag else None

                pp = Paper(title=paper_title, journal=paper_journal, year=year, pages=paper_pagination)

                for author in authors:
                    author_name = author.a.string if author.a else author.string
                    pp.authors.append(author_name)

                bibtex_tag = record.find("a", href=re.compile(".*view=bibtex.*"))
                pp.bibtex_url = bibtex_tag["href"] if bibtex_tag else None

                pp.calScore()
                if pp.score >= SCORE_THRESHOD:
                    paper_list.append(pp)
                    with open(filename, "a") as f:
                        writer = csv.writer(f)
                        writer.writerow([pp.title, pp.journal, pp.year, pp.pages, ", ".join(pp.authors), pp.bibtex_url])

        page += 1  # Increase page count

    logger.info(f"Found {len(paper_list)} papers for journal: {journal}")
    return paper_list

# Main function
if __name__ == "__main__":
    target_category = "journal"

    if target_category in venue_set:
        journals = venue_set[target_category]
        
        for journal in journals:
            logger.info(f"Starting search for journal: {journal}")
            searchJournal(journal, keywords, args.filename)
            logger.info(f"Completed search for journal: {journal}")