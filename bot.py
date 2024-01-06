import pywikibot
from pywikibot.bot import ExistingPageBot
from pywikibot import pagegenerators
from pywikibot.textlib import replace_links, extract_sections
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

### Configuration ###
pages = ['Wikipedia:Kahvihuone_(käytännöt)', 'Wikipedia:Kahvihuone_(Wikipedian_käytön_neuvonta)', 'Wikipedia:Kahvihuone_(sekalaista)', 'Wikipedia:Kahvihuone_(kielenhuolto)', 'Wikipedia:Kahvihuone_(tekniikka)', 'Wikipedia:Kahvihuone_(tekijänoikeudet)', 'Wikipedia:Kahvihuone_(uutiset)', 'Wikipedia:Kahvihuone_(kysy_vapaasti)']
archiveSuffix = "/Arkistohakemisto"
summary = 'Tiettyyn keskusteluun osoittavat linkit korjattu osoittamaan arkistoon (RaikastaBOT)'

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
                self.sections[neutralize(unquote(url.fragment))] = unquote(path + "#" + url.fragment);
                break 
        

class AnchoredLinkFixerBot(ExistingPageBot):
  sections = {}
  links_fixed = 0

  def parse_directory(self, page, pageName):
    # Arkistosivut käyttävät Luaa, joten täytyy etsiä keskustelujen otsikot HTML:stä
    parser = DirectoryLinkParser()
    parser.feed(page.get_parsed_page())

    self.sections[neutralize(pageName)] = {}
    for key, value in parser.sections.items():
      self.sections[neutralize(pageName)][key] = value

  def treat_page(self):
    if self.current_page.botMayEdit() == False: return

    text = replace_links(self.current_page.text, self.replace_callable, self.current_page.site)
    self.put_current(text, summary=summary)

  def replace_callable(self, link, text, groups, rng):
    page = groups["title"]
    section = groups["section"]

    # Jos linkki ei osoita johonkin tiettyyn alaotsikkoon, ohitetaan se
    if section == None:
      return

    print(f"Käsitellään linkki {page}#{section}")

    page = neutralize(page)
    section = neutralize(section)

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
        print("Haettua otsikkoa ei löytynyt: " + page + "#" + section)
    
    # Link all good!
    return

def main():
  site = pywikibot.Site('test', 'wikipedia')  # The site we want to run our bot on
  page = pywikibot.Page(site, 'User:Raikasta')
    
  # Käytetään väliaikaisesti muutamaa testisivua (test:User:Raikasta, test:User:Raikasta/Sandbox)
  # Kun otetaan testikäyttöön, haetaan page.backlinks() avulla sivujen IDt.
  # Ja rajataan ne vain artikkelien keskustelusivuihin, tms, mistä on puhe bottipyynnössä.
  generator = pagegenerators.PagesFromPageidGenerator("154167,154174", site)
  bot = AnchoredLinkFixerBot(generator=generator)

  print("Haetaan arkistohakemistot ja täytetään otsikkoindeksi...")
  for pageName in pages:
    archiveName = pageName + archiveSuffix
    bot.parse_directory(pywikibot.Page(pywikibot.Site('fi','wikipedia'), archiveName), pageName)

  print(f"Otsikkoindeksi on valmis. Käynnistetään botti.")

  bot.run()
  print(f"Botti suoritettu onnistuneesti. {bot.links_fixed} linkkiä korjattiin")

if __name__ == '__main__':
  main()
