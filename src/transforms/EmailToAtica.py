import re

from bs4 import BeautifulSoup
from maltego_trx.entities import Person, PhoneNumber, Email, Website
from maltego_trx.transform import DiscoverableTransform
from requests_html import HTMLSession
from .var.entities import *
from .var.fields import *


class EmailToAtica(DiscoverableTransform):
    URL_QUERY_ATICA = 'https://www.um.es/atica/directorio/?nivel=&lang=0&vista=unidades&search='
    URL_ATICA_DIR = 'https://www.um.es/atica/directorio/'
    EMAIl_UM_REGEX = '^[a-zA-Z0-9_.+-]+@um.es$'

    @classmethod
    def create_entities(cls, request, response):
        query_email = request.Value

        try:
            info = EmailToAtica.query(query_email)

            for name in info.keys():
                for value in info[name]:
                    if name == NAME[0]:
                        response.addEntity(Person, value)
                    elif name == KNOWLEDGE_DOMAIN[0]:
                        response.addEntity(KNOWLEDGE_DOMAIN_ENTITY, value)
                    elif name == ORGANIZATIONAL_UNIT[0]:
                        response.addEntity(ORGANIZATIONAL_UNIT_ENTITY, value)
                    elif name == TELEPHONE[0]:
                        response.addEntity(PhoneNumber, value)
                    elif name == EMAIL[0]:
                        response.addEntity(Email, value)
                    elif name == ALTERNATIVE_EMAIL[0]:
                        response.addEntity(Email, value)
                    elif name == STREET_ADDRESS[0]:
                        response.addEntity(STREET_ADDRESS_ENTITY, value)
                    elif name == CENTER[0]:
                        response.addEntity(CENTER_ENTITY, value)
                    elif name == JOB[0]:
                        response.addEntity(JOB_ENTITY, value)
                    elif name == POSITION[0]:
                        response.addEntity(POSITION_ENTITY, value)
                    elif name == OFFICE[0]:
                        response.addEntity(OFFICE_ENTITY, value)
                    elif name == AFFILIATION[0]:
                        response.addEntity(AFFILIATION_ENTITY, value)
                    elif name == PERSONAL_WEBSITE[0]:
                        response.addEntity(Website, value)
                    elif name == CURRICULUM[0]:
                        response.addEntity(CURRICULUM_ENTITY, value)
                    elif name == VCARD[0]:
                        response.addEntity(VCARD_ENTITY, value)

        except Exception as e:
            response.addUIMessage("Error: ")

        # Write the slider value as a UI message - just for fun
        response.addUIMessage("Slider value is at: " + str(request.Slider))


    @classmethod
    def query(cls, query_email):
        # check if valid email
        if not re.match(cls.EMAIl_UM_REGEX, query_email):
            raise Exception('This is not a valid email')

        # new session for requests
        session = HTMLSession()

        # query the email
        portal_query = session.get(cls.URL_QUERY_ATICA + query_email)

        # Scrapping
        query_soup = BeautifulSoup(portal_query.text,'html5lib')

        # check if there are entries
        entries_raw = query_soup.findAll('th',{'class':'numResult'})

        # Find targets
        # Parse number of entries
        # Possible 0  or multiple entries
        if entries_raw:
            number_entries = entries_raw[0].strong.get_text()

            # 0 entries, no result
            if number_entries == '0':
                return None

            targets = cls.get_targets(query_soup, session, query_email)
        else:
            # Directly found the target, obtain its href
            targets = [re.findall(r"\?nivel=.*", portal_query.url)[0]]

        if not targets:
            raise Exception("Something went wrong...")

        return cls.get_information(session,targets)

    @classmethod
    def get_targets(cls, query_soup, session, query_email):
        # Find the table with all people data
        body = query_soup.findAll('table', {'width': '100%', 'border': '0',
                                            'summary': 'Directorio corporativo de la Universidad de Murcia.'})[1].tbody
        # everyone's attributes
        people = body.findChildren(recursive=False)

        # Get href (target) to get information
        for person in people:
            # name and href (target)
            pair = person.findChildren(recursive=False)
            # name = pair[0].strong.get_text()

            # Check if multiple fields, (Dean, rector)
            targets_raw = pair[1].find_all('a', href=True)
            targets = []
            for i in range(0, len(targets_raw)):
                targets.append(targets_raw[i]['href'])

            # Only one person, stop
            if len(people) == 1:
                continue

            # Multiple results, select the exact matched email
            # Use the first field to check the email
            target = targets[0]

            # we need to render the html to obtain the mail due to javascript
            info = session.get(cls.URL_ATICA_DIR + target)
            info.html.render()

            # parse email
            info_soup = BeautifulSoup(info.html.html, 'html5lib')
            email_raw = info_soup.find('a', {'alt': "Enviar email"}, href=True)['href']
            email = re.findall(r"<.*>", email_raw)[0][1:-1]

            # if exact match stop
            if email == query_email:
                break

        return targets

    @classmethod
    def get_information(cls, session, targets):
        extracted_info = []
        for target in targets:
            # we need to render the html due to javascript
            info = session.get(cls.URL_ATICA_DIR + target,headers={"accept-encoding": "gzip"})
            info.html.render()

            # go to the where the information is
            info_soup = BeautifulSoup(info.html.html, 'html5lib',)
            info_raw = info_soup.find('table', {'border': '0','class':'infoElem','width':'400',
                                                 'summary':'Directorio corporativo de la Universidad de Murcia.'})

            # find different fields
            fields_raw = info_raw.tbody.findChildren(recursive=False)

            # Parse fields
            fields = {}
            for field_raw in fields_raw:
                parsed = cls.parse_raw_fields(field_raw)
                if parsed == None:
                    continue

                fields[parsed[0]] = parsed[1];

            extracted_info.append(fields)

        # Parse multiple information ( case of Dean)
        # If someone has different values for a field, they are appended to a list
        # Example: Affiliantion : [AffiliationA, AffiliantionB, AffiliationC]
        final_info={}
        for form in extracted_info:
            for field_name in form.keys():
                if field_name not in final_info:
                    final_info[field_name] = [form[field_name]]
                else:
                    if form[field_name] not in final_info[field_name]:
                        final_info[field_name].append(form[field_name])

        return final_info

    @classmethod
    def parse_raw_fields(cls, field_raw):
        # Extract field...
        field_name_raw = field_raw.find('td', {'class': 'derecha'})
        # vCard case
        if field_name_raw is None:
            field_name_raw = field_raw.find('td', {'class':'centra'}).find('a')
            # Unknown case
            if field_name_raw is None:
                return None

        # Parse fields and obtaing its value
        field_name = field_name_raw.text
        if field_name == NAME[1]:
            field_value = field_raw.find('span',{'itemprop': 'name'}).text
            field_name = NAME[0]

        elif field_name == KNOWLEDGE_DOMAIN[1] or field_name == CENTER[1]:
            field_value = field_raw.findAll('td')[1].text
            field_name = KNOWLEDGE_DOMAIN[0] if field_name == KNOWLEDGE_DOMAIN[1] else CENTER[0]

        elif field_name == TELEPHONE[1]:
            field_value = field_raw.find('span', {'itemprop': 'telephone'}).text
            field_name = TELEPHONE[0]

        elif field_name == EMAIL[1] or field_name == ALTERNATIVE_EMAIL[1]:
            email_raw = field_raw.find('a', {'alt': "Enviar email"}, href=True)['href']
            field_value = re.findall(r"<.*>", email_raw)[0][1:-1]
            field_name = EMAIL[0] if field_name == EMAIL[1] else ALTERNATIVE_EMAIL[0]

        elif field_name == STREET_ADDRESS[1]:
            field_value = field_raw.find('span', {'itemprop': 'streetAddress'}).text
            field_name = STREET_ADDRESS[0]

        elif field_name == JOB[1]:
            field_value = field_raw.find('span', {'itemprop': 'jobTitle'}).text
            field_name = JOB[0]

        elif field_name == OFFICE[1]:
            field_value = field_raw.find('a', {'itemprop': 'workLocation'}).text
            field_name = OFFICE[0]

        elif field_name == AFFILIATION[1] or field_name == PERSONAL_WEBSITE[1]\
                or field_name == POSITION[1] or field_name == ORGANIZATIONAL_UNIT[1]:
            field_value = field_raw.findAll('td')[1].text
            if field_name == AFFILIATION[1]:
                field_name = AFFILIATION[0]
            elif field_name == PERSONAL_WEBSITE[1]:
                field_name = PERSONAL_WEBSITE[0]
            elif field_name ==  POSITION[1]:
                field_name = POSITION[0]
            elif field_name ==  ORGANIZATIONAL_UNIT[1]:
                field_name = ORGANIZATIONAL_UNIT[0]

        elif field_name == CURRICULUM[1]:
            field_value = field_raw.find('a').text
            field_name = CURRICULUM[0]

        elif field_name == VCARD[1]:
            field_value = cls.URL_ATICA_DIR + field_raw.find('a')['href']
            field_name = VCARD[0]
        else:
            field_value = field_name = None

        return [field_name, field_value]


