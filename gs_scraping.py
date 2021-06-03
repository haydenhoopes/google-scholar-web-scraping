#!/usr/bin/env python
# coding: utf-8

# In[15]:


import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
import numpy as np
import json
import pathlib

params = {           # These should be modified by the user
    'year': '2020',
    'filepath': '../Downloads/20190607_OCIS member list - Copy.xlsx',
    'column_name': 'LastName, Name',
    'output_name': 'publications.xlsx'
}

BASE_URI = 'https://scholar.google.com'

list_of_authors = pd.DataFrame(pd.read_excel(params['filepath'], header=3))[params['column_name']].unique()


# ## Step 1: Pair all the authors with their user ID.

# In[5]:


def wait():
    time.sleep((8-5)*np.random.random()+5)


# In[6]:


# There is no way to know programmatically what an author's userId will be. However, to reduce the chance of including
# articles written by other authors of the same name, the program will select the most popular user with the given name.
# The userId can also be added manually.

def getUserIds(list_of_authors):
    auth_list_with_ids = []
    authors_without_profile = []
    count_without = 0 # get count of users with user profile
    for author in list_of_authors:
        ### Do stuff to get the id
        # Format the author's name
        name = author.replace(", ", "+").replace(" ", "+")
        
        # Google the author's name
        URI = BASE_URI + "/citations?view_op=search_authors&mauthors={}&hl=en&oi=ao"
        URL = URI.format(name)
        pattern = '(?<=user=)(.*)'
        wait()
        
        # Get the href of the a tag that goes to the profile page
        r = requests.get(URL).text
        soup = BeautifulSoup(r, 'html.parser')
        user = soup.find("h3")
        if user is None:
            count_without += 1
            authors_without_profile.append(author)
            print(f"user {author} did not have a profile")
#             raise Exception(f'No user was found. You may need to locate the User Id Manually for \'{author}\'')
        else:    
            user_url= user.a['href']

            # Extract the id from the href url
            scholarId = re.search(pattern, user_url).group(0)

            auth_list_with_ids.append({'name': author, 'scholarId': scholarId})
    print(f"{count_without} authors do not have profiles")    
    return auth_list_with_ids, authors_without_profile

author_list, authors_without_profile = getUserIds(list_of_authors)


# ## Step 2: Go through each authors' individual page, scraping the required data into a data frame.

# In[7]:


def getAuthorData(author_list):
    data = [] # While looping through authors and their publications, add data to list
    count = 0
    for author in author_list:
        # Make the URL, using the author's scholarId
        URI = BASE_URI + '/citations?hl=en&user={}&view_op=list_works&sortby=pubdate'
        URL = URI.format(author['scholarId'])
        
        
        # Get the page in HTML        
        # Google blocking: error handling
        req_finished = False
        while req_finished is False:
            wait()
            print("Request sent", end="\t")
            r = requests.get(URL).text
            soup = BeautifulSoup(r, 'html.parser')
            
            if soup.find("tbody", id='gsc_a_b') is None: # if the request is still blocked for some reason
                print("The request was blocked. Will try request again in two hours")
                time.sleep(7210) # wait for about two hours for Google to stop blocking and try again
            else:
                count += 1
                req_finished = True
                print(f"{count}: Request successful")
        
        # Get each table row of publication and filter by the given year
        for publication in soup.find("tbody", id='gsc_a_b').find_all("tr"):
            year = publication.find("td", class_='gsc_a_y').span.text


        # Get HTML of publications by year
            if year == params['year']:
                r = requests.get(BASE_URI + publication.find('a')['data-href']).text
                psoup = BeautifulSoup(r, 'html.parser')

        # If the publication was not a conference, keep going
                fields_keep = ['authors', 'publication_date', 'title', 'journal', 'volume', 'issue', 'pages', 'publisher']
                publication_entry = {}
                for k in psoup.find_all("div", class_="gs_scl"):
                    field = k.find('div', class_='gsc_vcd_field').text.lower().replace(" ", "_")
                    value = k.find('div', class_='gsc_vcd_value').text

                    if field in fields_keep:
                        publication_entry[field] = value
                        
                title = psoup.find('a', class_='gsc_vcd_title_link')
                if title is None:
                    title = psoup.find('div', id='gsc_vcd_title')
                publication_entry['title'] = title.text

        # Append the data entry to the data
                p_keys = publication_entry.keys()
                if "conference" not in p_keys and 'journal' in p_keys: # and 'volume' in p_keys and 'issue' in p_keys:
                    data.append(publication_entry)
    return data

data = getAuthorData(author_list)


# ## Step 4: Get data for authors without a Google Scholar profile

# In[8]:


# This step is to get publications data for members who do not have a Google Scholar profile. These results may
# be completely erroneous since they are matching members to articles based on name only and may contain data that
# is not relevant. Hopefully filtering the results by the same keywords as used above will allow some correct
# articles to be included which weren't included before.

# We already got the list of authors without a profile before --> authors_without_profile
pattern = '(?<=user=).+?(?=&)'
num_authors = len(authors_without_profile)
count = 0

for author in authors_without_profile:
    # Google the author's name
    URL = f"{BASE_URI}/scholar?q={author.replace(' ', '+')}&hl=en&as_sdt=0%2C45&as_ylo={params['year']}&as_yhi={params['year']}"
    
    # Get the href of the a tag that goes to the profile page
    r = requests.get(URL).text
    wait()
    soup = BeautifulSoup(r, 'html.parser')
    for publication in soup.find_all(class_="gs_r gs_or gs_scl"): # Get all of the articles that appear when you search the author's name
        
        article_title = publication.find("h3").find("a").text # This will be used later to get the article from a profile
        
        if publication.find(class_="gs_a").find('b') is not None:
            linked_authors_with_a_profile = [re.search(pattern, la['href']).group(0) for la in publication.find(class_="gs_a").find_all('a')]
            
            # We just got all of the authors with a scholar profile who were coauthors with the current author.
            # The next step is to go through the list of those profiled authors and see if they have information 
            # about the publication on their profile page. Sometimes this doesn't work because this program can't
            # load more items to a page so if the article doesn't show up on the first page, we'll try the next
            # profiled author.
            
            for a in linked_authors_with_a_profile:
                URL = f'{BASE_URI}/citations?hl=en&user={a}&view_op=list_works&sortby=pubdate'
                rr = requests.get(URL).text
                wait()
                asoup = BeautifulSoup(rr, 'html.parser')
                
                # Get each table row of publication and filter by the given year
                link_child = asoup.find(text=article_title)
                if link_child is not None:
                    link = link_child.parent['data-href']

                    # Get HTML of publications by year
                    rrr = requests.get(BASE_URI + link).text
                    wait()
                    psoup = BeautifulSoup(rrr, 'html.parser')

                # If the publication was not a conference, keep going
                    fields_keep = ['authors', 'publication_date', 'title', 'journal', 'volume', 'issue', 'pages', 'publisher']
                    publication_entry = {}
                    for k in psoup.find_all("div", class_="gs_scl"):
                        field = k.find('div', class_='gsc_vcd_field').text.lower().replace(" ", "_")
                        value = k.find('div', class_='gsc_vcd_value').text

                        if field in fields_keep:
                            publication_entry[field] = value

                    title = psoup.find('a', class_='gsc_vcd_title_link')
                    if title is None:
                        title = psoup.find('div', id='gsc_vcd_title')
                    publication_entry['title'] = title.text

            # Append the data entry to the data
                    p_keys = publication_entry.keys()
                    if "conference" not in p_keys: # and 'volume' in p_keys and 'issue' in p_keys:
                        data.append(publication_entry)
                        break
    count += 1                    
    print(f"{count}/{num_authors}: Author {author} was processed.")


# ## Step 5: Validate and clean the data by keyword

# In[115]:


df = pd.DataFrame(data).drop_duplicates(subset=['title', 'pages'])


keywords = ['data', 'information', 'organization', 'system', 'technology', 'software', 
            'digital', 'business', ' mis ', 'decision', 'code'] #This list is very important

df.dropna(inplace=True, subset=['journal'])
df['new_title'] = df['title'].apply(lambda x: None if not any(kw in x.lower() for kw in keywords) else x)
df['new_journal'] = df['journal'].apply(lambda x: None if not any(kw in x.lower() for kw in keywords) else x)

notkeywords = ['quarterly', 'conference', 'proceedings', 'cardiology', 'health', 'heart', 'medical', 'mammal', 'psychology', 'dermatology', 'disease', 'cell', 'tissue', 'medicine', 'oncology', 'astronomy', 'cystic', 'fibrosis']
df.dropna(inplace=True, subset=['new_journal', 'new_title'], how='all')
df['title'] = df['title'].apply(lambda x: None if any(nkw in x.lower() for nkw in notkeywords) else x)
df['journal'] = df['journal'].apply(lambda x: None if any(nkw in x.lower() for nkw in notkeywords) else x)

df.dropna(inplace=True, subset=['journal', 'title'])

df.drop(['new_title', 'new_journal'], inplace=True, axis=1)
print("Data successfully validated")


# ## Step 6: Export to Excel

# In[17]:


df.to_excel(params['output_name'], encoding="utf-16", index=False)
pth = f"{str(pathlib.Path(params['output_name']).parent.absolute())}/{params['output_name']}".replace("\\", '/')
print(f"Data exported successfully to {pth}")

