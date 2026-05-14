"""
fetch_and_process.py
--------------------
Fetches the latest NSE CM bhavcopy, filters to Nifty 500 constituents,
processes it with sector-level analysis, and fetches Reuters RSS news
headlines for top movers.

Writes data.json for index.html (GitHub Pages) to consume.

Run manually : python fetch_and_process.py
Run by CI    : same command, triggered by GitHub Actions on a schedule
"""

import io
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pandas as pd
import requests

# ── Nifty 500 constituent list (504 stocks as of April 30, 2026) ────────────
# (symbol, company name, sector)
NIFTY500_CONSTITUENTS = [
    ('360ONE', '360 ONE WAM Ltd.', 'Financial Services'),
    ('3MINDIA', '3M India Ltd.', 'Diversified'),
    ('ABB', 'ABB India Ltd.', 'Capital Goods'),
    ('ACC', 'ACC Ltd.', 'Construction Materials'),
    ('ACMESOLAR', 'ACME Solar Holdings Ltd.', 'Power'),
    ('AIAENG', 'AIA Engineering Ltd.', 'Capital Goods'),
    ('APLAPOLLO', 'APL Apollo Tubes Ltd.', 'Capital Goods'),
    ('AUBANK', 'AU Small Finance Bank Ltd.', 'Financial Services'),
    ('AWL', 'AWL Agri Business Ltd.', 'Fast Moving Consumer Goods'),
    ('AADHARHFC', 'Aadhar Housing Finance Ltd.', 'Financial Services'),
    ('AARTIIND', 'Aarti Industries Ltd.', 'Chemicals'),
    ('AAVAS', 'Aavas Financiers Ltd.', 'Financial Services'),
    ('ABBOTINDIA', 'Abbott India Ltd.', 'Healthcare'),
    ('ACE', 'Action Construction Equipment Ltd.', 'Capital Goods'),
    ('ACUTAAS', 'Acutaas Chemicals Ltd.', 'Healthcare'),
    ('ADANIENSOL', 'Adani Energy Solutions Ltd.', 'Power'),
    ('ADANIENT', 'Adani Enterprises Ltd.', 'Metals & Mining'),
    ('ADANIGREEN', 'Adani Green Energy Ltd.', 'Power'),
    ('ADANIPORTS', 'Adani Ports and Special Economic Zone Ltd.', 'Services'),
    ('ADANIPOWER', 'Adani Power Ltd.', 'Power'),
    ('ATGL', 'Adani Total Gas Ltd.', 'Oil Gas & Consumable Fuels'),
    ('ABCAPITAL', 'Aditya Birla Capital Ltd.', 'Financial Services'),
    ('ABFRL', 'Aditya Birla Fashion and Retail Ltd.', 'Consumer Services'),
    ('ABLBL', 'Aditya Birla Lifestyle Brands Ltd.', 'Consumer Services'),
    ('ABREL', 'Aditya Birla Real Estate Ltd.', 'Realty'),
    ('ABSLAMC', 'Aditya Birla Sun Life AMC Ltd.', 'Financial Services'),
    ('CPPLUS', 'Aditya Infotech Ltd.', 'Capital Goods'),
    ('AEGISLOG', 'Aegis Logistics Ltd.', 'Oil Gas & Consumable Fuels'),
    ('AEGISVOPAK', 'Aegis Vopak Terminals Ltd.', 'Oil Gas & Consumable Fuels'),
    ('AFCONS', 'Afcons Infrastructure Ltd.', 'Construction'),
    ('AFFLE', 'Affle 3i Ltd.', 'Information Technology'),
    ('AJANTPHARM', 'Ajanta Pharmaceuticals Ltd.', 'Healthcare'),
    ('ALKEM', 'Alkem Laboratories Ltd.', 'Healthcare'),
    ('ABDL', 'Allied Blenders and Distillers Ltd.', 'Fast Moving Consumer Goods'),
    ('ARE&M', 'Amara Raja Energy & Mobility Ltd.', 'Automobile and Auto Components'),
    ('AMBER', 'Amber Enterprises India Ltd.', 'Consumer Durables'),
    ('AMBUJACEM', 'Ambuja Cements Ltd.', 'Construction Materials'),
    ('ANANDRATHI', 'Anand Rathi Wealth Ltd.', 'Financial Services'),
    ('ANANTRAJ', 'Anant Raj Ltd.', 'Realty'),
    ('ANGELONE', 'Angel One Ltd.', 'Financial Services'),
    ('ANTHEM', 'Anthem Biosciences Ltd.', 'Healthcare'),
    ('ANURAS', 'Anupam Rasayan India Ltd.', 'Chemicals'),
    ('APARINDS', 'Apar Industries Ltd.', 'Capital Goods'),
    ('APOLLOHOSP', 'Apollo Hospitals Enterprise Ltd.', 'Healthcare'),
    ('APOLLOTYRE', 'Apollo Tyres Ltd.', 'Automobile and Auto Components'),
    ('APTUS', 'Aptus Value Housing Finance India Ltd.', 'Financial Services'),
    ('ASAHIINDIA', 'Asahi India Glass Ltd.', 'Automobile and Auto Components'),
    ('ASHOKLEY', 'Ashok Leyland Ltd.', 'Capital Goods'),
    ('ASIANPAINT', 'Asian Paints Ltd.', 'Consumer Durables'),
    ('ASTERDM', 'Aster DM Healthcare Ltd.', 'Healthcare'),
    ('ASTRAL', 'Astral Ltd.', 'Capital Goods'),
    ('ATHERENERG', 'Ather Energy Ltd.', 'Automobile and Auto Components'),
    ('ATUL', 'Atul Ltd.', 'Chemicals'),
    ('AUROPHARMA', 'Aurobindo Pharma Ltd.', 'Healthcare'),
    ('AIIL', 'Authum Investment & Infrastructure Ltd.', 'Financial Services'),
    ('DMART', 'Avenue Supermarts Ltd.', 'Consumer Services'),
    ('AXISBANK', 'Axis Bank Ltd.', 'Financial Services'),
    ('BEML', 'BEML Ltd.', 'Capital Goods'),
    ('BLS', 'BLS International Services Ltd.', 'Consumer Services'),
    ('BSE', 'BSE Ltd.', 'Financial Services'),
    ('BAJAJ-AUTO', 'Bajaj Auto Ltd.', 'Automobile and Auto Components'),
    ('BAJFINANCE', 'Bajaj Finance Ltd.', 'Financial Services'),
    ('BAJAJFINSV', 'Bajaj Finserv Ltd.', 'Financial Services'),
    ('BAJAJHLDNG', 'Bajaj Holdings & Investment Ltd.', 'Financial Services'),
    ('BAJAJHFL', 'Bajaj Housing Finance Ltd.', 'Financial Services'),
    ('BALKRISIND', 'Balkrishna Industries Ltd.', 'Automobile and Auto Components'),
    ('BALRAMCHIN', 'Balrampur Chini Mills Ltd.', 'Fast Moving Consumer Goods'),
    ('BANDHANBNK', 'Bandhan Bank Ltd.', 'Financial Services'),
    ('BANKBARODA', 'Bank of Baroda', 'Financial Services'),
    ('BANKINDIA', 'Bank of India', 'Financial Services'),
    ('MAHABANK', 'Bank of Maharashtra', 'Financial Services'),
    ('BATAINDIA', 'Bata India Ltd.', 'Consumer Durables'),
    ('BAYERCROP', 'Bayer Cropscience Ltd.', 'Chemicals'),
    ('BELRISE', 'Belrise Industries Ltd.', 'Automobile and Auto Components'),
    ('BERGEPAINT', 'Berger Paints India Ltd.', 'Consumer Durables'),
    ('BDL', 'Bharat Dynamics Ltd.', 'Capital Goods'),
    ('BEL', 'Bharat Electronics Ltd.', 'Capital Goods'),
    ('BHARATFORG', 'Bharat Forge Ltd.', 'Automobile and Auto Components'),
    ('BHEL', 'Bharat Heavy Electricals Ltd.', 'Capital Goods'),
    ('BPCL', 'Bharat Petroleum Corporation Ltd.', 'Oil Gas & Consumable Fuels'),
    ('BHARTIARTL', 'Bharti Airtel Ltd.', 'Telecommunication'),
    ('BHARTIHEXA', 'Bharti Hexacom Ltd.', 'Telecommunication'),
    ('BIKAJI', 'Bikaji Foods International Ltd.', 'Fast Moving Consumer Goods'),
    ('GROWW', 'Billionbrains Garage Ventures Ltd.', 'Financial Services'),
    ('BIOCON', 'Biocon Ltd.', 'Healthcare'),
    ('BSOFT', 'Birlasoft Ltd.', 'Information Technology'),
    ('BLUEDART', 'Blue Dart Express Ltd.', 'Services'),
    ('BLUEJET', 'Blue Jet Healthcare Ltd.', 'Healthcare'),
    ('BLUESTARCO', 'Blue Star Ltd.', 'Consumer Durables'),
    ('BBTC', 'Bombay Burmah Trading Corporation Ltd.', 'Fast Moving Consumer Goods'),
    ('BOSCHLTD', 'Bosch Ltd.', 'Automobile and Auto Components'),
    ('FIRSTCRY', 'Brainbees Solutions Ltd.', 'Consumer Services'),
    ('BRIGADE', 'Brigade Enterprises Ltd.', 'Realty'),
    ('BRITANNIA', 'Britannia Industries Ltd.', 'Fast Moving Consumer Goods'),
    ('MAPMYINDIA', 'C.E. Info Systems Ltd.', 'Information Technology'),
    ('CCL', 'CCL Products (I) Ltd.', 'Fast Moving Consumer Goods'),
    ('CESC', 'CESC Ltd.', 'Power'),
    ('CGPOWER', 'CG Power and Industrial Solutions Ltd.', 'Capital Goods'),
    ('CIEINDIA', 'CIE Automotive India Ltd.', 'Automobile and Auto Components'),
    ('CRISIL', 'CRISIL Ltd.', 'Financial Services'),
    ('CANFINHOME', 'Can Fin Homes Ltd.', 'Financial Services'),
    ('CANBK', 'Canara Bank', 'Financial Services'),
    ('CANHLIFE', 'Canara HSBC Life Insurance Company Ltd.', 'Financial Services'),
    ('CAPLIPOINT', 'Caplin Point Laboratories Ltd.', 'Healthcare'),
    ('CGCL', 'Capri Global Capital Ltd.', 'Financial Services'),
    ('CARBORUNIV', 'Carborundum Universal Ltd.', 'Capital Goods'),
    ('CARTRADE', 'Cartrade Tech Ltd.', 'Consumer Services'),
    ('CASTROLIND', 'Castrol India Ltd.', 'Oil Gas & Consumable Fuels'),
    ('CEATLTD', 'Ceat Ltd.', 'Automobile and Auto Components'),
    ('CEMPRO', 'Cemindia Projects Ltd.', 'Construction'),
    ('CENTRALBK', 'Central Bank of India', 'Financial Services'),
    ('CDSL', 'Central Depository Services (India) Ltd.', 'Financial Services'),
    ('CHALET', 'Chalet Hotels Ltd.', 'Consumer Services'),
    ('CHAMBLFERT', 'Chambal Fertilizers & Chemicals Ltd.', 'Chemicals'),
    ('CHENNPETRO', 'Chennai Petroleum Corporation Ltd.', 'Oil Gas & Consumable Fuels'),
    ('CHOICEIN', 'Choice International Ltd.', 'Financial Services'),
    ('CHOLAHLDNG', 'Cholamandalam Financial Holdings Ltd.', 'Financial Services'),
    ('CHOLAFIN', 'Cholamandalam Investment and Finance Company Ltd.', 'Financial Services'),
    ('CIPLA', 'Cipla Ltd.', 'Healthcare'),
    ('CUB', 'City Union Bank Ltd.', 'Financial Services'),
    ('CLEAN', 'Clean Science and Technology Ltd.', 'Chemicals'),
    ('COALINDIA', 'Coal India Ltd.', 'Oil Gas & Consumable Fuels'),
    ('COCHINSHIP', 'Cochin Shipyard Ltd.', 'Capital Goods'),
    ('COFORGE', 'Coforge Ltd.', 'Information Technology'),
    ('COHANCE', 'Cohance Lifesciences Ltd.', 'Healthcare'),
    ('COLPAL', 'Colgate Palmolive (India) Ltd.', 'Fast Moving Consumer Goods'),
    ('CAMS', 'Computer Age Management Services Ltd.', 'Financial Services'),
    ('CONCORDBIO', 'Concord Biotech Ltd.', 'Healthcare'),
    ('CONCOR', 'Container Corporation of India Ltd.', 'Services'),
    ('COROMANDEL', 'Coromandel International Ltd.', 'Chemicals'),
    ('CRAFTSMAN', 'Craftsman Automation Ltd.', 'Automobile and Auto Components'),
    ('CREDITACC', 'CreditAccess Grameen Ltd.', 'Financial Services'),
    ('CROMPTON', 'Crompton Greaves Consumer Electricals Ltd.', 'Consumer Durables'),
    ('CUMMINSIND', 'Cummins India Ltd.', 'Capital Goods'),
    ('CYIENT', 'Cyient Ltd.', 'Information Technology'),
    ('DCMSHRIRAM', 'DCM Shriram Ltd.', 'Diversified'),
    ('DLF', 'DLF Ltd.', 'Realty'),
    ('DOMS', 'DOMS Industries Ltd.', 'Fast Moving Consumer Goods'),
    ('DABUR', 'Dabur India Ltd.', 'Fast Moving Consumer Goods'),
    ('DALBHARAT', 'Dalmia Bharat Ltd.', 'Construction Materials'),
    ('DATAPATTNS', 'Data Patterns (India) Ltd.', 'Capital Goods'),
    ('DEEPAKFERT', 'Deepak Fertilisers & Petrochemicals Corp. Ltd.', 'Chemicals'),
    ('DEEPAKNTR', 'Deepak Nitrite Ltd.', 'Chemicals'),
    ('DELHIVERY', 'Delhivery Ltd.', 'Services'),
    ('DEVYANI', 'Devyani International Ltd.', 'Consumer Services'),
    ('DIVISLAB', "Divi's Laboratories Ltd.", 'Healthcare'),
    ('DIXON', 'Dixon Technologies (India) Ltd.', 'Consumer Durables'),
    ('LALPATHLAB', 'Dr. Lal Path Labs Ltd.', 'Healthcare'),
    ('DRREDDY', "Dr. Reddy's Laboratories Ltd.", 'Healthcare'),
    ('EIDPARRY', 'E.I.D. Parry (India) Ltd.', 'Fast Moving Consumer Goods'),
    ('EIHOTEL', 'EIH Ltd.', 'Consumer Services'),
    ('EICHERMOT', 'Eicher Motors Ltd.', 'Automobile and Auto Components'),
    ('ELECON', 'Elecon Engineering Co. Ltd.', 'Capital Goods'),
    ('ELGIEQUIP', 'Elgi Equipments Ltd.', 'Capital Goods'),
    ('EMAMILTD', 'Emami Ltd.', 'Fast Moving Consumer Goods'),
    ('EMCURE', 'Emcure Pharmaceuticals Ltd.', 'Healthcare'),
    ('EMMVEE', 'Emmvee Photovoltaic Power Ltd.', 'Capital Goods'),
    ('ENDURANCE', 'Endurance Technologies Ltd.', 'Automobile and Auto Components'),
    ('ENGINERSIN', 'Engineers India Ltd.', 'Construction'),
    ('ERIS', 'Eris Lifesciences Ltd.', 'Healthcare'),
    ('ESCORTS', 'Escorts Kubota Ltd.', 'Capital Goods'),
    ('ETERNAL', 'Eternal Ltd.', 'Consumer Services'),
    ('EXIDEIND', 'Exide Industries Ltd.', 'Automobile and Auto Components'),
    ('NYKAA', 'FSN E-Commerce Ventures Ltd.', 'Consumer Services'),
    ('FEDERALBNK', 'Federal Bank Ltd.', 'Financial Services'),
    ('FACT', 'Fertilisers and Chemicals Travancore Ltd.', 'Chemicals'),
    ('FINCABLES', 'Finolex Cables Ltd.', 'Capital Goods'),
    ('FSL', 'Firstsource Solutions Ltd.', 'Services'),
    ('FIVESTAR', 'Five-Star Business Finance Ltd.', 'Financial Services'),
    ('FORCEMOT', 'Force Motors Ltd.', 'Automobile and Auto Components'),
    ('FORTIS', 'Fortis Healthcare Ltd.', 'Healthcare'),
    ('GAIL', 'GAIL (India) Ltd.', 'Oil Gas & Consumable Fuels'),
    ('GVT&D', 'GE Vernova T&D India Ltd.', 'Capital Goods'),
    ('GMRAIRPORT', 'GMR Airports Ltd.', 'Services'),
    ('GABRIEL', 'Gabriel India Ltd.', 'Automobile and Auto Components'),
    ('GALLANTT', 'Gallantt Ispat Ltd.', 'Capital Goods'),
    ('GRSE', 'Garden Reach Shipbuilders & Engineers Ltd.', 'Capital Goods'),
    ('GICRE', 'General Insurance Corporation of India', 'Financial Services'),
    ('GILLETTE', 'Gillette India Ltd.', 'Fast Moving Consumer Goods'),
    ('GLAND', 'Gland Pharma Ltd.', 'Healthcare'),
    ('GLAXO', 'Glaxosmithkline Pharmaceuticals Ltd.', 'Healthcare'),
    ('GLENMARK', 'Glenmark Pharmaceuticals Ltd.', 'Healthcare'),
    ('MEDANTA', 'Global Health Ltd.', 'Healthcare'),
    ('GODIGIT', 'Go Digit General Insurance Ltd.', 'Financial Services'),
    ('GPIL', 'Godawari Power & Ispat Ltd.', 'Capital Goods'),
    ('GODFRYPHLP', 'Godfrey Phillips India Ltd.', 'Fast Moving Consumer Goods'),
    ('GODREJCP', 'Godrej Consumer Products Ltd.', 'Fast Moving Consumer Goods'),
    ('GODREJIND', 'Godrej Industries Ltd.', 'Diversified'),
    ('GODREJPROP', 'Godrej Properties Ltd.', 'Realty'),
    ('GRANULES', 'Granules India Ltd.', 'Healthcare'),
    ('GRAPHITE', 'Graphite India Ltd.', 'Capital Goods'),
    ('GRASIM', 'Grasim Industries Ltd.', 'Construction Materials'),
    ('GRAVITA', 'Gravita India Ltd.', 'Metals & Mining'),
    ('GESHIP', 'Great Eastern Shipping Co. Ltd.', 'Services'),
    ('FLUOROCHEM', 'Gujarat Fluorochemicals Ltd.', 'Chemicals'),
    ('GMDCLTD', 'Gujarat Mineral Development Corporation Ltd.', 'Metals & Mining'),
    ('HEG', 'H.E.G. Ltd.', 'Capital Goods'),
    ('HBLENGINE', 'HBL Engineering Ltd.', 'Capital Goods'),
    ('HCLTECH', 'HCL Technologies Ltd.', 'Information Technology'),
    ('HDBFS', 'HDB Financial Services Ltd.', 'Financial Services'),
    ('HDFCAMC', 'HDFC Asset Management Company Ltd.', 'Financial Services'),
    ('HDFCBANK', 'HDFC Bank Ltd.', 'Financial Services'),
    ('HDFCLIFE', 'HDFC Life Insurance Company Ltd.', 'Financial Services'),
    ('HFCL', 'HFCL Ltd.', 'Telecommunication'),
    ('HAVELLS', 'Havells India Ltd.', 'Consumer Durables'),
    ('HEROMOTOCO', 'Hero MotoCorp Ltd.', 'Automobile and Auto Components'),
    ('HEXT', 'Hexaware Technologies Ltd.', 'Information Technology'),
    ('HSCL', 'Himadri Speciality Chemical Ltd.', 'Chemicals'),
    ('HINDALCO', 'Hindalco Industries Ltd.', 'Metals & Mining'),
    ('HAL', 'Hindustan Aeronautics Ltd.', 'Capital Goods'),
    ('HINDCOPPER', 'Hindustan Copper Ltd.', 'Metals & Mining'),
    ('HINDPETRO', 'Hindustan Petroleum Corporation Ltd.', 'Oil Gas & Consumable Fuels'),
    ('HINDUNILVR', 'Hindustan Unilever Ltd.', 'Fast Moving Consumer Goods'),
    ('HINDZINC', 'Hindustan Zinc Ltd.', 'Metals & Mining'),
    ('POWERINDIA', 'Hitachi Energy India Ltd.', 'Capital Goods'),
    ('HOMEFIRST', 'Home First Finance Company India Ltd.', 'Financial Services'),
    ('HONASA', 'Honasa Consumer Ltd.', 'Fast Moving Consumer Goods'),
    ('HONAUT', 'Honeywell Automation India Ltd.', 'Capital Goods'),
    ('HUDCO', 'Housing & Urban Development Corporation Ltd.', 'Financial Services'),
    ('HYUNDAI', 'Hyundai Motor India Ltd.', 'Automobile and Auto Components'),
    ('ICICIBANK', 'ICICI Bank Ltd.', 'Financial Services'),
    ('ICICIGI', 'ICICI Lombard General Insurance Company Ltd.', 'Financial Services'),
    ('ICICIAMC', 'ICICI Prudential Asset Management Company Ltd.', 'Financial Services'),
    ('ICICIPRULI', 'ICICI Prudential Life Insurance Company Ltd.', 'Financial Services'),
    ('IDBI', 'IDBI Bank Ltd.', 'Financial Services'),
    ('IDFCFIRSTB', 'IDFC First Bank Ltd.', 'Financial Services'),
    ('IFCI', 'IFCI Ltd.', 'Financial Services'),
    ('IIFL', 'IIFL Finance Ltd.', 'Financial Services'),
    ('IRB', 'IRB Infrastructure Developers Ltd.', 'Construction'),
    ('IRCON', 'IRCON International Ltd.', 'Construction'),
    ('ITCHOTELS', 'ITC Hotels Ltd.', 'Consumer Services'),
    ('ITC', 'ITC Ltd.', 'Fast Moving Consumer Goods'),
    ('ITI', 'ITI Ltd.', 'Telecommunication'),
    ('INDGN', 'Indegene Ltd.', 'Healthcare'),
    ('INDIACEM', 'India Cements Ltd.', 'Construction Materials'),
    ('INDIAMART', 'Indiamart Intermesh Ltd.', 'Consumer Services'),
    ('INDIANB', 'Indian Bank', 'Financial Services'),
    ('IEX', 'Indian Energy Exchange Ltd.', 'Financial Services'),
    ('INDHOTEL', 'Indian Hotels Co. Ltd.', 'Consumer Services'),
    ('IOC', 'Indian Oil Corporation Ltd.', 'Oil Gas & Consumable Fuels'),
    ('IOB', 'Indian Overseas Bank', 'Financial Services'),
    ('IRCTC', 'Indian Railway Catering And Tourism Corporation Ltd.', 'Consumer Services'),
    ('IRFC', 'Indian Railway Finance Corporation Ltd.', 'Financial Services'),
    ('IREDA', 'Indian Renewable Energy Development Agency Ltd.', 'Financial Services'),
    ('IGL', 'Indraprastha Gas Ltd.', 'Oil Gas & Consumable Fuels'),
    ('INDUSTOWER', 'Indus Towers Ltd.', 'Telecommunication'),
    ('INDUSINDBK', 'IndusInd Bank Ltd.', 'Financial Services'),
    ('NAUKRI', 'Info Edge (India) Ltd.', 'Consumer Services'),
    ('INFY', 'Infosys Ltd.', 'Information Technology'),
    ('INOXWIND', 'Inox Wind Ltd.', 'Capital Goods'),
    ('INTELLECT', 'Intellect Design Arena Ltd.', 'Information Technology'),
    ('INDIGO', 'InterGlobe Aviation Ltd.', 'Services'),
    ('IGIL', 'International Gemological Institute Ltd.', 'Services'),
    ('IKS', 'Inventurus Knowledge Solutions Ltd.', 'Information Technology'),
    ('IPCALAB', 'Ipca Laboratories Ltd.', 'Healthcare'),
    ('JBCHEPHARM', 'J.B. Chemicals & Pharmaceuticals Ltd.', 'Healthcare'),
    ('JKCEMENT', 'J.K. Cement Ltd.', 'Construction Materials'),
    ('JBMA', 'JBM Auto Ltd.', 'Automobile and Auto Components'),
    ('JKTYRE', 'JK Tyre & Industries Ltd.', 'Automobile and Auto Components'),
    ('JMFINANCIL', 'JM Financial Ltd.', 'Financial Services'),
    ('JSWCEMENT', 'JSW Cement Ltd.', 'Construction Materials'),
    ('JSWENERGY', 'JSW Energy Ltd.', 'Power'),
    ('JSWINFRA', 'JSW Infrastructure Ltd.', 'Services'),
    ('JSWSTEEL', 'JSW Steel Ltd.', 'Metals & Mining'),
    ('JAINREC', 'Jain Resource Recycling Ltd.', 'Metals & Mining'),
    ('JPPOWER', 'Jaiprakash Power Ventures Ltd.', 'Power'),
    ('J&KBANK', 'Jammu & Kashmir Bank Ltd.', 'Financial Services'),
    ('JINDALSAW', 'Jindal Saw Ltd.', 'Capital Goods'),
    ('JSL', 'Jindal Stainless Ltd.', 'Metals & Mining'),
    ('JINDALSTEL', 'Jindal Steel Ltd.', 'Metals & Mining'),
    ('JIOFIN', 'Jio Financial Services Ltd.', 'Financial Services'),
    ('JUBLFOOD', 'Jubilant Foodworks Ltd.', 'Consumer Services'),
    ('JUBLINGREA', 'Jubilant Ingrevia Ltd.', 'Chemicals'),
    ('JUBLPHARMA', 'Jubilant Pharmova Ltd.', 'Healthcare'),
    ('JWL', 'Jupiter Wagons Ltd.', 'Capital Goods'),
    ('JYOTICNC', 'Jyoti CNC Automation Ltd.', 'Capital Goods'),
    ('KPRMILL', 'K.P.R. Mill Ltd.', 'Textiles'),
    ('KEI', 'KEI Industries Ltd.', 'Capital Goods'),
    ('KPITTECH', 'KPIT Technologies Ltd.', 'Information Technology'),
    ('KAJARIACER', 'Kajaria Ceramics Ltd.', 'Consumer Durables'),
    ('KPIL', 'Kalpataru Projects International Ltd.', 'Construction'),
    ('KALYANKJIL', 'Kalyan Jewellers India Ltd.', 'Consumer Durables'),
    ('KARURVYSYA', 'Karur Vysya Bank Ltd.', 'Financial Services'),
    ('KAYNES', 'Kaynes Technology India Ltd.', 'Capital Goods'),
    ('KEC', 'Kec International Ltd.', 'Construction'),
    ('KFINTECH', 'Kfin Technologies Ltd.', 'Financial Services'),
    ('KIRLOSENG', 'Kirloskar Oil Eng Ltd.', 'Capital Goods'),
    ('KOTAKBANK', 'Kotak Mahindra Bank Ltd.', 'Financial Services'),
    ('KIMS', 'Krishna Institute of Medical Sciences Ltd.', 'Healthcare'),
    ('LTF', 'L&T Finance Ltd.', 'Financial Services'),
    ('LTTS', 'L&T Technology Services Ltd.', 'Information Technology'),
    ('LGEINDIA', 'LG Electronics India Ltd.', 'Consumer Durables'),
    ('LICHSGFIN', 'LIC Housing Finance Ltd.', 'Financial Services'),
    ('LTFOODS', 'LT Foods Ltd.', 'Fast Moving Consumer Goods'),
    ('LT', 'Larsen & Toubro Ltd.', 'Construction'),
    ('LATENTVIEW', 'Latent View Analytics Ltd.', 'Information Technology'),
    ('LAURUSLABS', 'Laurus Labs Ltd.', 'Healthcare'),
    ('THELEELA', 'Leela Palaces Hotels & Resorts Ltd.', 'Consumer Services'),
    ('LEMONTREE', 'Lemon Tree Hotels Ltd.', 'Consumer Services'),
    ('LICI', 'Life Insurance Corporation of India', 'Financial Services'),
    ('LINDEINDIA', 'Linde India Ltd.', 'Chemicals'),
    ('LLOYDSME', 'Lloyds Metals And Energy Ltd.', 'Metals & Mining'),
    ('LODHA', 'Lodha Developers Ltd.', 'Realty'),
    ('LUPIN', 'Lupin Ltd.', 'Healthcare'),
    ('MMTC', 'MMTC Ltd.', 'Services'),
    ('MRF', 'MRF Ltd.', 'Automobile and Auto Components'),
    ('MGL', 'Mahanagar Gas Ltd.', 'Oil Gas & Consumable Fuels'),
    ('M&MFIN', 'Mahindra & Mahindra Financial Services Ltd.', 'Financial Services'),
    ('M&M', 'Mahindra & Mahindra Ltd.', 'Automobile and Auto Components'),
    ('MANAPPURAM', 'Manappuram Finance Ltd.', 'Financial Services'),
    ('MRPL', 'Mangalore Refinery & Petrochemicals Ltd.', 'Oil Gas & Consumable Fuels'),
    ('MANKIND', 'Mankind Pharma Ltd.', 'Healthcare'),
    ('MARICO', 'Marico Ltd.', 'Fast Moving Consumer Goods'),
    ('MARUTI', 'Maruti Suzuki India Ltd.', 'Automobile and Auto Components'),
    ('MFSL', 'Max Financial Services Ltd.', 'Financial Services'),
    ('MAXHEALTH', 'Max Healthcare Institute Ltd.', 'Healthcare'),
    ('MAZDOCK', 'Mazagoan Dock Shipbuilders Ltd.', 'Capital Goods'),
    ('MINDACORP', 'Minda Corporation Ltd.', 'Automobile and Auto Components'),
    ('MSUMI', 'Motherson Sumi Wiring India Ltd.', 'Automobile and Auto Components'),
    ('MOTILALOFS', 'Motilal Oswal Financial Services Ltd.', 'Financial Services'),
    ('MPHASIS', 'MphasiS Ltd.', 'Information Technology'),
    ('MCX', 'Multi Commodity Exchange of India Ltd.', 'Financial Services'),
    ('MUTHOOTFIN', 'Muthoot Finance Ltd.', 'Financial Services'),
    ('NATCOPHARM', 'NATCO Pharma Ltd.', 'Healthcare'),
    ('NBCC', 'NBCC (India) Ltd.', 'Construction'),
    ('NCC', 'NCC Ltd.', 'Construction'),
    ('NHPC', 'NHPC Ltd.', 'Power'),
    ('NLCINDIA', 'NLC India Ltd.', 'Power'),
    ('NMDC', 'NMDC Ltd.', 'Metals & Mining'),
    ('NSLNISP', 'NMDC Steel Ltd.', 'Metals & Mining'),
    ('NTPCGREEN', 'NTPC Green Energy Ltd.', 'Power'),
    ('NTPC', 'NTPC Ltd.', 'Power'),
    ('NH', 'Narayana Hrudayalaya Ltd.', 'Healthcare'),
    ('NATIONALUM', 'National Aluminium Co. Ltd.', 'Metals & Mining'),
    ('NAVA', 'Nava Ltd.', 'Power'),
    ('NAVINFLUOR', 'Navin Fluorine International Ltd.', 'Chemicals'),
    ('NESTLEIND', 'Nestle India Ltd.', 'Fast Moving Consumer Goods'),
    ('NETWEB', 'Netweb Technologies India Ltd.', 'Information Technology'),
    ('NEULANDLAB', 'Neuland Laboratories Ltd.', 'Healthcare'),
    ('NEWGEN', 'Newgen Software Technologies Ltd.', 'Information Technology'),
    ('NAM-INDIA', 'Nippon Life India Asset Management Ltd.', 'Financial Services'),
    ('NIVABUPA', 'Niva Bupa Health Insurance Company Ltd.', 'Financial Services'),
    ('NUVAMA', 'Nuvama Wealth Management Ltd.', 'Financial Services'),
    ('NUVOCO', 'Nuvoco Vistas Corporation Ltd.', 'Construction Materials'),
    ('OBEROIRLTY', 'Oberoi Realty Ltd.', 'Realty'),
    ('ONGC', 'Oil & Natural Gas Corporation Ltd.', 'Oil Gas & Consumable Fuels'),
    ('OIL', 'Oil India Ltd.', 'Oil Gas & Consumable Fuels'),
    ('OLAELEC', 'Ola Electric Mobility Ltd.', 'Automobile and Auto Components'),
    ('OLECTRA', 'Olectra Greentech Ltd.', 'Automobile and Auto Components'),
    ('PAYTM', 'One 97 Communications Ltd.', 'Financial Services'),
    ('OFSS', 'Oracle Financial Services Software Ltd.', 'Information Technology'),
    ('POLICYBZR', 'PB Fintech Ltd.', 'Financial Services'),
    ('PCBL', 'PCBL Chemical Ltd.', 'Chemicals'),
    ('PGEL', 'PG Electroplast Ltd.', 'Consumer Durables'),
    ('PIIND', 'PI Industries Ltd.', 'Chemicals'),
    ('PNBHOUSING', 'PNB Housing Finance Ltd.', 'Financial Services'),
    ('PVRINOX', 'PVR INOX Ltd.', 'Media Entertainment & Publication'),
    ('PAGEIND', 'Page Industries Ltd.', 'Textiles'),
    ('PARADEEP', 'Paradeep Phosphates Ltd.', 'Chemicals'),
    ('PATANJALI', 'Patanjali Foods Ltd.', 'Fast Moving Consumer Goods'),
    ('PERSISTENT', 'Persistent Systems Ltd.', 'Information Technology'),
    ('PETRONET', 'Petronet LNG Ltd.', 'Oil Gas & Consumable Fuels'),
    ('PFIZER', 'Pfizer Ltd.', 'Healthcare'),
    ('PHOENIXLTD', 'Phoenix Mills Ltd.', 'Realty'),
    ('PIDILITIND', 'Pidilite Industries Ltd.', 'Chemicals'),
    ('PIRAMALFIN', 'Piramal Finance Ltd.', 'Financial Services'),
    ('PPLPHARMA', 'Piramal Pharma Ltd.', 'Healthcare'),
    ('POLYMED', 'Poly Medicure Ltd.', 'Healthcare'),
    ('POLYCAB', 'Polycab India Ltd.', 'Capital Goods'),
    ('POONAWALLA', 'Poonawalla Fincorp Ltd.', 'Financial Services'),
    ('PFC', 'Power Finance Corporation Ltd.', 'Financial Services'),
    ('POWERGRID', 'Power Grid Corporation of India Ltd.', 'Power'),
    ('PREMIERENE', 'Premier Energies Ltd.', 'Capital Goods'),
    ('PRESTIGE', 'Prestige Estates Projects Ltd.', 'Realty'),
    ('PNB', 'Punjab National Bank', 'Financial Services'),
    ('RRKABEL', 'R R Kabel Ltd.', 'Capital Goods'),
    ('RBLBANK', 'RBL Bank Ltd.', 'Financial Services'),
    ('RECLTD', 'REC Ltd.', 'Financial Services'),
    ('RITES', 'RITES Ltd.', 'Construction'),
    ('RADICO', 'Radico Khaitan Ltd', 'Fast Moving Consumer Goods'),
    ('RVNL', 'Rail Vikas Nigam Ltd.', 'Construction'),
    ('RAILTEL', 'Railtel Corporation Of India Ltd.', 'Telecommunication'),
    ('RAINBOW', 'Rainbow Childrens Medicare Ltd.', 'Healthcare'),
    ('RKFORGE', 'Ramkrishna Forgings Ltd.', 'Automobile and Auto Components'),
    ('REDINGTON', 'Redington Ltd.', 'Services'),
    ('RELIANCE', 'Reliance Industries Ltd.', 'Oil Gas & Consumable Fuels'),
    ('SBFC', 'SBFC Finance Ltd.', 'Financial Services'),
    ('SBICARD', 'SBI Cards and Payment Services Ltd.', 'Financial Services'),
    ('SBILIFE', 'SBI Life Insurance Company Ltd.', 'Financial Services'),
    ('SJVN', 'SJVN Ltd.', 'Power'),
    ('SRF', 'SRF Ltd.', 'Chemicals'),
    ('SAGILITY', 'Sagility Ltd.', 'Information Technology'),
    ('SAILIFE', 'Sai Life Sciences Ltd.', 'Healthcare'),
    ('MOTHERSON', 'Samvardhana Motherson International Ltd.', 'Automobile and Auto Components'),
    ('SAPPHIRE', 'Sapphire Foods India Ltd.', 'Consumer Services'),
    ('SAREGAMA', 'Saregama India Ltd', 'Media Entertainment & Publication'),
    ('SCHAEFFLER', 'Schaeffler India Ltd.', 'Automobile and Auto Components'),
    ('SCHNEIDER', 'Schneider Electric Infrastructure Ltd.', 'Capital Goods'),
    ('SCI', 'Shipping Corporation of India Ltd.', 'Services'),
    ('SHREECEM', 'Shree Cement Ltd.', 'Construction Materials'),
    ('SHRIRAMFIN', 'Shriram Finance Ltd.', 'Financial Services'),
    ('SHYAMMETL', 'Shyam Metalics and Energy Ltd.', 'Capital Goods'),
    ('SIEMENS', 'Siemens Ltd.', 'Capital Goods'),
    ('SOBHA', 'Sobha Ltd.', 'Realty'),
    ('SOLARINDS', 'Solar Industries India Ltd.', 'Chemicals'),
    ('SONACOMS', 'Sona BLW Precision Forgings Ltd.', 'Automobile and Auto Components'),
    ('SONATSOFTW', 'Sonata Software Ltd.', 'Information Technology'),
    ('STARHEALTH', 'Star Health and Allied Insurance Company Ltd.', 'Financial Services'),
    ('SBIN', 'State Bank of India', 'Financial Services'),
    ('SAIL', 'Steel Authority of India Ltd.', 'Metals & Mining'),
    ('SUMICHEM', 'Sumitomo Chemical India Ltd.', 'Chemicals'),
    ('SUNPHARMA', 'Sun Pharmaceutical Industries Ltd.', 'Healthcare'),
    ('SUNTV', 'Sun TV Network Ltd.', 'Media Entertainment & Publication'),
    ('SUNDARMFIN', 'Sundaram Finance Ltd.', 'Financial Services'),
    ('SUPREMEIND', 'Supreme Industries Ltd.', 'Capital Goods'),
    ('SUZLON', 'Suzlon Energy Ltd.', 'Capital Goods'),
    ('SWIGGY', 'Swiggy Ltd.', 'Consumer Services'),
    ('SYNGENE', 'Syngene International Ltd.', 'Healthcare'),
    ('SYRMA', 'Syrma SGS Technology Ltd.', 'Capital Goods'),
    ('TVSMOTOR', 'TVS Motor Company Ltd.', 'Automobile and Auto Components'),
    ('TATACAP', 'Tata Capital Ltd.', 'Financial Services'),
    ('TATACHEM', 'Tata Chemicals Ltd.', 'Chemicals'),
    ('TATACOMM', 'Tata Communications Ltd.', 'Telecommunication'),
    ('TCS', 'Tata Consultancy Services Ltd.', 'Information Technology'),
    ('TATACONSUM', 'Tata Consumer Products Ltd.', 'Fast Moving Consumer Goods'),
    ('TATAELXSI', 'Tata Elxsi Ltd.', 'Information Technology'),
    ('TATAINVEST', 'Tata Investment Corporation Ltd.', 'Financial Services'),
    ('TATAPOWER', 'Tata Power Co. Ltd.', 'Power'),
    ('TATASTEEL', 'Tata Steel Ltd.', 'Metals & Mining'),
    ('TATATECH', 'Tata Technologies Ltd.', 'Information Technology'),
    ('TECHM', 'Tech Mahindra Ltd.', 'Information Technology'),
    ('TITAN', 'Titan Company Ltd.', 'Consumer Durables'),
    ('TORNTPHARM', 'Torrent Pharmaceuticals Ltd.', 'Healthcare'),
    ('TORNTPOWER', 'Torrent Power Ltd.', 'Power'),
    ('TRENT', 'Trent Ltd.', 'Consumer Services'),
    ('TRIDENT', 'Trident Ltd.', 'Textiles'),
    ('TIINDIA', 'Tube Investments of India Ltd.', 'Automobile and Auto Components'),
    ('UCOBANK', 'UCO Bank', 'Financial Services'),
    ('UNOMINDA', 'UNO Minda Ltd.', 'Automobile and Auto Components'),
    ('UPL', 'UPL Ltd.', 'Chemicals'),
    ('UTIAMC', 'UTI Asset Management Company Ltd.', 'Financial Services'),
    ('ULTRACEMCO', 'UltraTech Cement Ltd.', 'Construction Materials'),
    ('UNIONBANK', 'Union Bank of India', 'Financial Services'),
    ('UBL', 'United Breweries Ltd.', 'Fast Moving Consumer Goods'),
    ('UNITDSPR', 'United Spirits Ltd.', 'Fast Moving Consumer Goods'),
    ('VTL', 'Vardhman Textiles Ltd.', 'Textiles'),
    ('VBL', 'Varun Beverages Ltd.', 'Fast Moving Consumer Goods'),
    ('VEDL', 'Vedanta Ltd.', 'Metals & Mining'),
    ('VIJAYA', 'Vijaya Diagnostic Centre Ltd.', 'Healthcare'),
    ('VMM', 'Vishal Mega Mart Ltd.', 'Consumer Services'),
    ('IDEA', 'Vodafone Idea Ltd.', 'Telecommunication'),
    ('VOLTAS', 'Voltas Ltd.', 'Consumer Durables'),
    ('WAAREEENER', 'Waaree Energies Ltd.', 'Capital Goods'),
    ('WELCORP', 'Welspun Corp Ltd.', 'Capital Goods'),
    ('WELSPUNLIV', 'Welspun Living Ltd.', 'Textiles'),
    ('WHIRLPOOL', 'Whirlpool of India Ltd.', 'Consumer Durables'),
    ('WIPRO', 'Wipro Ltd.', 'Information Technology'),
    ('WOCKPHARMA', 'Wockhardt Ltd.', 'Healthcare'),
    ('YESBANK', 'Yes Bank Ltd.', 'Financial Services'),
    ('ZEEL', 'Zee Entertainment Enterprises Ltd.', 'Media Entertainment & Publication'),
    ('ZYDUSLIFE', 'Zydus Lifesciences Ltd.', 'Healthcare'),
    ('ZYDUSWELL', 'Zydus Wellness Ltd.', 'Fast Moving Consumer Goods'),
    ('ECLERX', 'eClerx Services Ltd.', 'Services'),
]

# Build lookup sets/dicts
N500_SYMBOLS   = {s for s, _, _ in NIFTY500_CONSTITUENTS}
N500_COMPANY   = {s: c for s, c, _ in NIFTY500_CONSTITUENTS}
N500_SECTOR    = {s: sec for s, _, sec in NIFTY500_CONSTITUENTS}

# ── NSE URL helpers ────────────────────────────────────────────────────────────
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

COLUMN_ALIASES = {
    "PrvsClsgPric": "PREV_CL_PR",
    "OpnPric": "OPEN_PRICE",
    "HghPric": "HIGH_PRICE",
    "LwPric": "LOW_PRICE",
    "ClsPric": "CLOSE_PRICE",
    "LastPric": "LAST_PRICE",
    "TtlTrfVal": "NET_TRDVAL",
    "TtlTradgVol": "NET_TRDQTY",
    "TtlNbOfTxsExctd": "TRADES",
    "TckrSymb": "SECURITY",
    "SctySrs": "MKT",
    "PREVCLOSE": "PREV_CL_PR",
    "PREV_CLOSE": "PREV_CL_PR",
    "OPEN": "OPEN_PRICE",
    "HIGH": "HIGH_PRICE",
    "LOW": "LOW_PRICE",
    "CLOSE": "CLOSE_PRICE",
    "LAST": "CLOSE_PRICE",
    "LAST_PRICE": "CLOSE_PRICE",
    "TOTTRDVAL": "NET_TRDVAL",
    "TOTALTRDVAL": "NET_TRDVAL",
    "TOTTRDQTY": "NET_TRDQTY",
    "TOTALTRDQTY": "NET_TRDQTY",
    "52WH": "HI_52_WK",
    "52WL": "LO_52_WK",
    "HIGH52": "HI_52_WK",
    "LOW52": "LO_52_WK",
    "SYMBOL": "SECURITY",
    "SCRIP_NM": "SECURITY",
    "SERIES": "MKT",
    "TOTALTRADES": "TRADES",
    "NO_OF_TRADES": "TRADES",
}


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    rename_map = {}
    for col in df.columns:
        if col in COLUMN_ALIASES:
            canonical = COLUMN_ALIASES[col]
            if canonical not in df.columns and canonical not in rename_map.values():
                rename_map[col] = canonical
    if rename_map:
        print(f"  Column rename: {rename_map}")
        df = df.rename(columns=rename_map)
    if "CLOSE_PRICE" not in df.columns and "LAST_PRICE" in df.columns:
        df = df.rename(columns={"LAST_PRICE": "CLOSE_PRICE"})
    return df


def bhavcopy_urls(d: date) -> list:
    ds = d.strftime("%Y%m%d")
    base = "https://nsearchives.nseindia.com/content/cm/"
    return [
        f"{base}BhavCopy_NSE_CM_0_0_0_{ds}_F_0000.csv.zip",
        f"{base}BhavCopy_NSE_CM_0_0_0_{ds}_F.CSV.zip",
    ]


def fetch_latest_bhavcopy() -> tuple:
    session = requests.Session()
    session.get("https://www.nseindia.com/all-reports", headers=NSE_HEADERS, timeout=10)
    for days_back in range(0, 11):
        trade_date = date.today() - timedelta(days=days_back)
        for url in bhavcopy_urls(trade_date):
            print(f"Trying {url} ...")
            try:
                resp = session.get(url, headers=NSE_HEADERS, timeout=30)
                if resp.status_code == 200:
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                        csv_name = z.namelist()[0]
                        with z.open(csv_name) as f:
                            df = pd.read_csv(f)
                    df = normalise_columns(df)
                    print(f"✓ Fetched bhavcopy for {trade_date} ({len(df)} rows)")
                    return df, trade_date
            except Exception as e:
                print(f"  Error: {e} — skipping")
    raise RuntimeError("Could not fetch bhavcopy for the last 10 days.")


# ── Reuters RSS news for a company/symbol ─────────────────────────────────────
# Uses Reuters search RSS — free, no API key required.
# Returns up to max_items headlines as [{"title": ..., "url": ..., "published": ...}]

def fetch_reuters_news(query: str, max_items: int = 3) -> list:
    """Fetch headlines from Reuters RSS for a search query."""
    # Reuters search RSS endpoint
    url = f"https://feeds.reuters.com/reuters/INbusinessNews"
    # We'll fetch general India business news and filter by company name
    # since Reuters doesn't offer per-stock RSS without a paid API.
    # For production, swap this with a NewsAPI / Bing News / Google News RSS call.
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NSEDashboard/1.0)"
    }
    results = []
    try:
        # Use Google News RSS which is free and has good NSE coverage
        encoded = requests.utils.quote(query + " India stock NSE")
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        resp = requests.get(rss_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:max_items]:
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                # Strip Google redirect wrapping
                source_tag = item.find("{https://news.google.com/rss}source")
                source = source_tag.text if source_tag is not None else ""
                if title:
                    results.append({
                        "title": title,
                        "url": link,
                        "published": pub,
                        "source": source,
                    })
    except Exception as e:
        print(f"  News fetch failed for '{query}': {e}")
    return results


def fetch_news_for_movers(gainers: list, losers: list) -> dict:
    """Fetch news for top 5 gainers and top 5 losers. Returns {symbol: [articles]}."""
    news = {}
    movers = gainers[:5] + losers[:5]
    for row in movers:
        sym = row.get("security", "")
        company = N500_COMPANY.get(sym, sym)
        print(f"  Fetching news for {sym} ({company}) ...")
        articles = fetch_reuters_news(company, max_items=3)
        news[sym] = articles
        time.sleep(0.4)   # gentle rate-limiting
    return news


# ── Processing ─────────────────────────────────────────────────────────────────
def safe_float(val):
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def process(df: pd.DataFrame) -> dict:
    num_cols = [
        "PREV_CL_PR", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE",
        "CLOSE_PRICE", "NET_TRDVAL", "NET_TRDQTY", "TRADES",
        "HI_52_WK", "LO_52_WK",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # ── Filter to Nifty 500 constituents ──────────────────────────────────────
    if "SECURITY" in df.columns:
        n500_df = df[df["SECURITY"].isin(N500_SYMBOLS)].copy()
        print(f"  Nifty 500 filter: {len(df)} → {len(n500_df)} rows matched")
    else:
        print("  WARNING: SECURITY column missing; using all rows")
        n500_df = df.copy()

    # Attach company name and sector
    n500_df["COMPANY"]  = n500_df["SECURITY"].map(N500_COMPANY).fillna(n500_df["SECURITY"])
    n500_df["SECTOR"]   = n500_df["SECURITY"].map(N500_SECTOR).fillna("Other")

    # Active rows (traded today)
    if "TRADES" in n500_df.columns:
        active = n500_df[n500_df["TRADES"] > 0].copy()
    else:
        active = n500_df.copy()

    active["CHANGE"]     = active["CLOSE_PRICE"] - active["PREV_CL_PR"]
    active["CHANGE_PCT"] = (active["CHANGE"] / active["PREV_CL_PR"]) * 100

    if "HIGH_PRICE" in active.columns and "LOW_PRICE" in active.columns:
        active["HL_RANGE_PCT"] = (
            (active["HIGH_PRICE"] - active["LOW_PRICE"]) / active["CLOSE_PRICE"] * 100
        )

    # ── Summary breadth stats ─────────────────────────────────────────────────
    gainers   = int((active["CHANGE_PCT"] > 0).sum())
    losers    = int((active["CHANGE_PCT"] < 0).sum())
    unchanged = int((active["CHANGE_PCT"] == 0).sum())
    total_act = gainers + losers + unchanged

    summary = {
        "totalConstituents": len(N500_SYMBOLS),
        "activeRows": len(active),
        "gainers": gainers,
        "losers": losers,
        "unchanged": unchanged,
        "advanceDeclineRatio": round(gainers / losers, 2) if losers else None,
        "breadthPct": round(gainers / total_act * 100, 1) if total_act else None,
        "totalMarketValue": round(float(active["NET_TRDVAL"].sum()), 0)
            if "NET_TRDVAL" in active.columns else None,
        "meanChangePct": round(float(active["CHANGE_PCT"].mean()), 2),
        "medianChangePct": round(float(active["CHANGE_PCT"].median()), 2),
        "stdChangePct": round(float(active["CHANGE_PCT"].std()), 2),
    }

    # ── Sector-level analysis ─────────────────────────────────────────────────
    sector_stats = []
    for sector, grp in active.groupby("SECTOR"):
        g = int((grp["CHANGE_PCT"] > 0).sum())
        l = int((grp["CHANGE_PCT"] < 0).sum())
        sector_stats.append({
            "sector": sector,
            "count": len(grp),
            "gainers": g,
            "losers": l,
            "avgChangePct": round(float(grp["CHANGE_PCT"].mean()), 2),
            "totalValue": round(float(grp["NET_TRDVAL"].sum()), 0)
                if "NET_TRDVAL" in grp.columns else None,
        })
    sector_stats.sort(key=lambda x: x["avgChangePct"], reverse=True)

    # ── Top gainers / losers ──────────────────────────────────────────────────
    def top_rows(frame, n=10, ascending=False):
        fn = frame.nsmallest if ascending else frame.nlargest
        rows = []
        for _, r in fn(n, "CHANGE_PCT").iterrows():
            if pd.isna(r.get("CLOSE_PRICE")):
                continue
            rows.append({
                "security": str(r["SECURITY"]),
                "company": str(r.get("COMPANY", r["SECURITY"])),
                "sector": str(r.get("SECTOR", "")),
                "prevClose": safe_float(r["PREV_CL_PR"]),
                "close": safe_float(r["CLOSE_PRICE"]),
                "changePct": safe_float(r["CHANGE_PCT"]),
                "tradeValue": round(float(r["NET_TRDVAL"]), 0)
                    if "NET_TRDVAL" in frame.columns and pd.notna(r.get("NET_TRDVAL")) else None,
            })
        return rows

    top_gainers = top_rows(active, n=10, ascending=False)
    top_losers  = top_rows(active, n=10, ascending=True)

    # ── Most traded (by value, within Nifty 500) ──────────────────────────────
    most_traded = []
    if "NET_TRDVAL" in active.columns:
        for _, r in active.nlargest(15, "NET_TRDVAL").iterrows():
            most_traded.append({
                "security": str(r["SECURITY"]),
                "company": str(r.get("COMPANY", r["SECURITY"])),
                "sector": str(r.get("SECTOR", "")),
                "close": safe_float(r["CLOSE_PRICE"]),
                "changePct": safe_float(r["CHANGE_PCT"]),
                "tradeValue": round(float(r["NET_TRDVAL"]), 0),
            })

    # ── Return distribution (Nifty 500 only) ─────────────────────────────────
    bins   = [-100, -10, -5, -2, 0, 2, 5, 10, 100]
    labels = ["<-10%", "-10 to -5%", "-5 to -2%", "-2 to 0%",
              "0 to 2%", "2 to 5%", "5 to 10%", ">10%"]
    active["bucket"] = pd.cut(active["CHANGE_PCT"], bins=bins, labels=labels)
    dist = active["bucket"].value_counts().sort_index()

    # ── 52-week proximity ─────────────────────────────────────────────────────
    near52High, near52Low = [], []
    if "HI_52_WK" in active.columns and "LO_52_WK" in active.columns:
        nh = active[
            (active["CLOSE_PRICE"] > 0) & (active["HI_52_WK"] > 0) &
            (active["CLOSE_PRICE"] >= active["HI_52_WK"] * 0.97)
        ]
        nl = active[
            (active["CLOSE_PRICE"] > 0) & (active["LO_52_WK"] > 0) &
            (active["CLOSE_PRICE"] <= active["LO_52_WK"] * 1.03)
        ]
        near52High = [
            {
                "security": str(r["SECURITY"]),
                "company": str(r.get("COMPANY", r["SECURITY"])),
                "close": safe_float(r["CLOSE_PRICE"]),
                "high52": safe_float(r["HI_52_WK"]),
                "pctFromHigh": round((float(r["CLOSE_PRICE"]) / float(r["HI_52_WK"]) - 1) * 100, 2),
            }
            for _, r in nh.nlargest(20, "CLOSE_PRICE").iterrows()
        ]
        near52Low = [
            {
                "security": str(r["SECURITY"]),
                "company": str(r.get("COMPANY", r["SECURITY"])),
                "close": safe_float(r["CLOSE_PRICE"]),
                "low52": safe_float(r["LO_52_WK"]),
                "pctFromLow": round((float(r["CLOSE_PRICE"]) / float(r["LO_52_WK"]) - 1) * 100, 2),
            }
            for _, r in nl.nsmallest(20, "CLOSE_PRICE").iterrows()
        ]

    # ── Fetch news for top movers ─────────────────────────────────────────────
    print("Fetching news for top movers...")
    news_map = fetch_news_for_movers(top_gainers, top_losers)

    # Attach news to gainer/loser rows
    for row in top_gainers + top_losers:
        row["news"] = news_map.get(row["security"], [])

    return {
        "summary": summary,
        "sectorStats": sector_stats,
        "topGainers": top_gainers,
        "topLosers": top_losers,
        "mostTradedByValue": most_traded,
        "distribution": {
            "labels": labels,
            "values": [int(dist.get(l, 0)) for l in labels],
        },
        "near52High": near52High,
        "near52Low": near52Low,
    }


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    df, trade_date = fetch_latest_bhavcopy()
    data = process(df)
    data["date"] = trade_date.strftime("%d %b %Y")
    data["indexInfo"] = {
        "name": "Nifty 500",
        "constituents": len(N500_SYMBOLS),
        "methodology": "Free Float Market Capitalisation",
        "rebalancing": "Semi-Annual (Jan 31 & Jul 31)",
        "baseDate": "January 01, 1995",
        "baseValue": 1000,
    }

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"✓ data.json written — {trade_date} ({data['summary']['activeRows']} Nifty 500 stocks)")
