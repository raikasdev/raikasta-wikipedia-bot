import pywikibot
from pywikibot.bot import ExistingPageBot
from pywikibot import pagegenerators
from pywikibot.textlib import extract_sections
from replacer import replace_links
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote, quote
import requests 
import datetime
import json
import sys
import traceback

# Config pywikibot
pywikibot.config.max_retries = 2
pywikibot.config.put_throttle = 5
pywikibot.config.retry_wait = 2
pywikibot.config.retry_max = 5

### Configuration ###
pages = ['Wikipedia:Kahvihuone_(käytännöt)', 'Wikipedia:Kahvihuone_(Wikipedian_käytön_neuvonta)', 'Wikipedia:Kahvihuone_(sekalaista)', 'Wikipedia:Kahvihuone_(kielenhuolto)', 'Wikipedia:Kahvihuone_(tekniikka)', 'Wikipedia:Kahvihuone_(tekijänoikeudet)', 'Wikipedia:Kahvihuone_(uutiset)', 'Wikipedia:Kahvihuone_(kysy_vapaasti)']
archiveSuffixes = ["/Arkistohakemisto", "/Arkistohakemisto/1–20", "/Arkistohakemisto/21–40"]
namespaces = [1, 4, 5, 12, 13] # Keskustelu, Wikipedia, Keskustelu Wikipediasta, Ohje, Keskustelu Ohjeesta
site = pywikibot.Site('fi', 'wikipedia') # The site we want to run our bot on

### Super Epic Function by ChatGPT ###
def find_closest_value(data, target_timestamp):
  if not data:
    return None  # Return None if the array is empty

  # Convert the target timestamp to a datetime object
  target_datetime = datetime.datetime.utcfromtimestamp(target_timestamp)

  # Sort the array of dictionaries based on the absolute difference between timestamps
  sorted_data = sorted(data, key=lambda x: abs(x['date'] - target_timestamp))

  # Return the value from the dictionary with the closest timestamp
  return sorted_data[0]['url']

### The bot itself ###
def neutralize(str):
    # Tekee tekstistä samanlaisen (ei välilyöntejä vaan alaviivat, pienet kirjaimet), jotta tekstien vertailu on helpompaa
    return str.replace(" ", "_").lower()

class DirectoryLinkParser(HTMLParser):
    def __init__(self, pageName):
      super().__init__()
      self.page = pageName
      self.archiveDates = {}
      self.sections = {}

    def handle_starttag(self, tag, attrs):
        if not tag == "a": return
        for key, value in attrs:
            if key == "href":
                url = urlsplit(value)
                if url.fragment == "" or url.fragment == None:
                  print(f"Empty fragment, skip ({value})")
                  continue

                path = "/".join(url.path.split("/")[2:])
                if path == "" or path == None:
                  print(f"Invalid path, skip ({value})")
                  continue

                date = 0
                if path in self.archiveDates:
                  date = self.archiveDates[path]
                else:
                  page = pywikibot.Page(site, path)
                  if page.exists():
                    date = latest_edit_timestamp(page)
                    self.archiveDates[path] = date

                obj = {
                  "url": unquote(path + "#" + url.fragment).replace("_", " "),
                  "date": date
                }

                key1 = neutralize(unquote(url.fragment))
                key2 = neutralize(quote(url.fragment).replace("%","."))

                arr = []
                if key1 in self.sections:
                  arr = self.sections[key1]

                arr.append(obj)
                self.sections[key1] = arr
                self.sections[key2] = arr
                
                print(unquote(path + "#" + url.fragment).replace("_", " ") + " archived")
                break 
        

class AnchoredLinkFixerBot(ExistingPageBot):
  sections = {}
  links_fixed = 0
  pages_fixed = 0
  links_not_found = []
  temp_links_fixed = 0

  def parse_directory(self, page, pageName):
    # Arkistosivut käyttävät Luaa, joten täytyy etsiä keskustelujen otsikot HTML:stä
    parser = DirectoryLinkParser(pageName)
    parser.feed(page.get_parsed_page())

    self.sections[neutralize(pageName)] = {}
    for key, value in parser.sections.items():
      self.sections[neutralize(pageName)][key] = value

  def treat_page(self):
    if self.current_page.botMayEdit() == False: return
    self.temp_links_fixed = 0
    try:
      text = replace_links(self.current_page.text, self.replace_callable, self.current_page.site)
      if (text != self.current_page.text):
        self.pages_fixed += 1
      self.put_current(text, summary=f"{self.temp_links_fixed} vanhentunutta keskustelulinkkiä päivitetty osoittamaan arkistoon")
    except Exception as e:
      print("Sivua parsetessa tapahtui virhe. Ulkoisen palvelun API-virhe?")
      print(e)
      traceback.print_exc()
      pass

  def replace_callable(self, link, text, groups, rng):
    page = groups["title"]
    section = groups["section"]

    # Jos linkki ei osoita johonkin tiettyyn alaotsikkoon, ohitetaan se
    if section == None:
      return

    print(f"Käsitellään linkki {page}#{section}")

    page = neutralize(page)
    section = neutralize(unquote(section))

    # Onko linkki sivulle, jota etsitään (esim. Wikipedia:Kahvihuone_(sekalaista))
    if page in self.sections:
      sections = self.sections[page]
      if section in sections:
        self.links_fixed += 1
        self.temp_links_fixed += 1
        
        entryCount = len(sections[section])

        # Go back history enough to find latest non-minor and non-bot edit
        revisions = self.current_page.revisions()
        
        latestTimestamp = latest_edit_timestamp(self.current_page)
        newPage = find_closest_value(sections[section], latestTimestamp)

        # Muodostetaan linkki-wikitext
        label = groups["label"]
        if label != '' and label != None:
          label = f"|{label}"
        else:
          originalPage = groups["title"]
          originalSection = groups["section"]
          label = f"|{originalPage}#{originalSection}"
        print(f"Linkki korjattu! ({newPage}{label}) ajalla {latestTimestamp}")
        return f"[[{newPage}{label}]]"
      else:
        self.links_not_found.append(page + "#" + section)
        print("Haettua otsikkoa ei löytynyt: " + page + "#" + section)

    # Link all good!
    return

def latest_edit_timestamp(page):
  revisions = list(page.revisions())

  for revision in revisions:
    if revision.minor == True:
      continue
    if "bot" in revision.user.lower():
      continue
    if "bot" in revision.comment.lower():
      continue
    return revision.timestamp.posix_timestamp()

  # Or return oldest edit
  return revisions[-1].timestamp.posix_timestamp()

def main():
  print("Haetaan sivut...")
  ids = []
  for pageName in pages:
   page = pywikibot.Page(site, pageName)
   subPages = page.backlinks(namespaces=namespaces)
   for subPage in subPages:
     if subPage.pageid != 0:
       ids.append(subPage.pageid)

  generator = pagegenerators.PagesFromPageidGenerator([561234], site)
  bot = AnchoredLinkFixerBot(generator=generator)

  if len(sys.argv) == 2 and sys.argv[1] == "build":
    print("Haetaan arkistohakemistot ja täytetään otsikkoindeksi...")
    for pageName in pages:
      for archiveSuffix in archiveSuffixes:
        archiveName = pageName + archiveSuffix
        archivePage = pywikibot.Page(site, archiveName)
        if archivePage.exists() == False:
          continue
        bot.parse_directory(archivePage, pageName)

    with open('discussion_index.json', 'w') as json_file:
      json.dump(bot.sections, json_file, indent=2)
  else:
    bot.sections = json.load(open('discussion_index.json'))

  print(f"Otsikkoindeksi on valmis. Käynnistetään botti.")

  bot.run()
  print(f"Botti suoritettu onnistuneesti. {bot.links_fixed} linkkiä korjattiin {bot.pages_fixed} sivulla")
  print("Seuraavia sivuja ei löytynyt: (" + str(len(bot.links_not_found)) + " kpl)")
  print(", ".join(bot.links_not_found))

if __name__ == '__main__':
  page = pywikibot.Page(site, "Wikipedia:Kahvihuone (tekniikka)/Arkisto8")
  main()

