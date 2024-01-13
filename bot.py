import pywikibot
from pywikibot.bot import ExistingPageBot
from pywikibot import pagegenerators
from pywikibot.textlib import extract_sections, replace_links
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote, quote
import requests 

# Config pywikibot
pywikibot.config.max_retries = 2
pywikibot.config.put_throttle = 5

### Configuration ###
pages = ['Wikipedia:Kahvihuone_(käytännöt)', 'Wikipedia:Kahvihuone_(Wikipedian_käytön_neuvonta)', 'Wikipedia:Kahvihuone_(sekalaista)', 'Wikipedia:Kahvihuone_(kielenhuolto)', 'Wikipedia:Kahvihuone_(tekniikka)', 'Wikipedia:Kahvihuone_(tekijänoikeudet)', 'Wikipedia:Kahvihuone_(uutiset)', 'Wikipedia:Kahvihuone_(kysy_vapaasti)']
archiveSuffixes = ["/Arkistohakemisto", "/Arkistohakemisto/1–20", "/Arkistohakemisto/21–40"]
summary = 'Tiettyyn keskusteluun osoittavat linkit korjattu osoittamaan arkistoon (automaattinen)'
namespaces = [1, 4, 5, 12, 13] # Keskustelu, Wikipedia, Keskustelu Wikipediasta, Ohje, Keskustelu Ohjeesta

### The bot itself ###
def neutralize(str):
    # Tekee tekstistä samanlaisen (ei välilyöntejä vaan alaviivat, pienet kirjaimet), jotta tekstien vertailu on helpompaa
    return str.replace(" ", "_").lower()

class DirectoryLinkParser(HTMLParser):
    sections = {}
    
    def handle_starttag(self, tag, attrs):
        if not tag == "a": return
        for key, value in attrs:
            if key == "href":
                url = urlsplit(value)
                path = "/".join(url.path.split("/")[2:])
                self.sections[neutralize(unquote(url.fragment))] = unquote(path + "#" + url.fragment).replace("_", " ")
                self.sections[neutralize(quote(url.fragment).replace("%","."))] = unquote(path + "#" + url.fragment).replace("_", " ")
                break 
        

class AnchoredLinkFixerBot(ExistingPageBot):
  sections = {}
  links_fixed = 0
  pages_fixed = 0
  links_not_found = []
  
  def parse_directory(self, page, pageName):
    # Arkistosivut käyttävät Luaa, joten täytyy etsiä keskustelujen otsikot HTML:stä
    parser = DirectoryLinkParser()
    parser.feed(page.get_parsed_page())

    self.sections[neutralize(pageName)] = {}
    for key, value in parser.sections.items():
      self.sections[neutralize(pageName)][key] = value

  def treat_page(self):
    if self.current_page.botMayEdit() == False: return

    try:
      text = replace_links(self.current_page.text, self.replace_callable, self.current_page.site)
      if (text != self.current_page.text):
        self.pages_fixed += 1
      self.put_current(text, summary=summary)
    except Exception:
      print("Sivua parsetessa tapahtui virhe. Ulkoisen palvelun API-virhe?")
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
        print("Linkki korjattu!")
        
        # Muodostetaan linkki-wikitext
        label = groups["label"]
        if label != '' and label != None:
          label = f"|{label}"
        else:
          label = ""
        return f"[[{sections[section]}{label}]]"
      else:
        self.links_not_found.append(page + "#" + section)
        print("Haettua otsikkoa ei löytynyt: " + page + "#" + section)

    # Link all good!
    return

def main():
  site = pywikibot.Site('fi', 'wikipedia')  # The site we want to run our bot on

  print("Haetaan sivut...")
  ids = []
  for pageName in pages:
   page = pywikibot.Page(site, pageName)
   subPages = page.backlinks(namespaces=namespaces)
   for subPage in subPages:
     if subPage.pageid != 0:
       ids.append(subPage.pageid)

  generator = pagegenerators.PagesFromPageidGenerator(ids, site)
  bot = AnchoredLinkFixerBot(generator=generator)

  print("Haetaan arkistohakemistot ja täytetään otsikkoindeksi...")
  for pageName in pages:
    for archiveSuffix in archiveSuffixes:
      archiveName = pageName + archiveSuffix
      archivePage = pywikibot.Page(site, archiveName)
      if archivePage.exists() == False:
        continue
      bot.parse_directory(archivePage, pageName)

  print(f"Otsikkoindeksi on valmis. Käynnistetään botti.")

  bot.run()
  print(f"Botti suoritettu onnistuneesti. {bot.links_fixed} linkkiä korjattiin {bot.pages_fixed} sivulla")
  print("Seuraavia sivuja ei löytynyt: (" + str(len(bot.links_not_found)) + " kpl)")
  print(", ".join(bot.links_not_found))

if __name__ == '__main__':
  main()

