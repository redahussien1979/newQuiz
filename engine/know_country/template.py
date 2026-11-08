"""Builds the Excel template for the Know a Country tab (projects/know_country_template.xlsx)."""
import json, os
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))

COLUMNS = [
    ("country", "English name or 3-letter code (Japan / JPN)", "Japan"),
    ("brand", "Channel handle shown at the top (leave empty for @Ma3loomaFast)", "@Ma3loomaFast"),
    ("name_ar", "Arabic name (leave empty to use the built-in name)", "اليابان"),
    ("capital_ar", "Capital in Arabic", "طوكيو"),
    ("capital_lat", "Capital latitude (decimal)", 35.68),
    ("capital_lon", "Capital longitude (decimal)", 139.69),
    ("area_km2", "Official total area, km²", 377980),
    ("area_date_ar", "Date of the area figure (Arabic)", "يوليو 2025"),
    ("area_date_en", "Date of the area figure (English)", "July 2025"),
    ("population", "Population (whole number)", 122690000),
    ("population_date_ar", "Date of the population figure (Arabic)", "أكتوبر 2026"),
    ("population_date_en", "Date of the population figure (English)", "October 2026"),
    ("language_ar", "Main language (Arabic)", "اليابانية"),
    ("language_en", "Main language (English)", "Japanese"),
    ("currency_ar", "Currency (Arabic)", "الين الياباني"),
    ("currency_en", "Currency (English)", "Japanese yen"),
    ("currency_symbol", "Currency symbol", "¥"),
    ("compare_with", "4-5 countries to drag the country onto, comma separated (English names or codes)",
     "Germany, Egypt, Saudi Arabia, United Arab Emirates"),
    ("nearby", "Neighbours to show. Islands: neighbours across the sea. Land countries: leave EMPTY to use the real land borders automatically, or list them yourself",
     "Russia, South Korea, North Korea, China"),
    ("distance_from", "4-5 cities to measure the distance from (names from the 'cities' sheet)",
     "Dubai, Riyadh, Cairo, London, New York"),
    ("exports_year_ar", "Year of the export figures (Arabic)", "2025"),
    ("exports_year_en", "Year of the export figures (English)", "2025"),
    ("exports_total_ar", "Total exports (Arabic)", "110.4 تريليون ين"),
    ("exports_total_en", "Total exports (English)", "¥110.4 trillion"),
    ("export1_ar", "Top export 1 (Arabic)", "السيارات"),
    ("export1_en", "Top export 1 (English)", "Motor vehicles"),
    ("export1_share", "Top export 1: % of total exports", 15.9),
    ("export1_icon", "Icon: car, cpu, building-factory-2, droplet (oil), wheat, diamond, shirt, pill, device-mobile, bolt, ship, package",
     "car"),
    ("export2_ar", "Top export 2 (Arabic)", "أشباه الموصلات"),
    ("export2_en", "Top export 2 (English)", "Semiconductors"),
    ("export2_share", "Top export 2: % of total exports", 6.0),
    ("export2_icon", "Icon for export 2", "cpu"),
    ("export3_ar", "Top export 3 (Arabic)", "معدات تصنيع أشباه الموصلات"),
    ("export3_en", "Top export 3 (English)", "Semiconductor machinery"),
    ("export3_share", "Top export 3: % of total exports", 4.1),
    ("export3_icon", "Icon for export 3", "building-factory-2"),
    ("exports_source_ar", "Source of the export figures (Arabic)", "المصدر: الجمارك اليابانية - وزارة المالية"),
    ("exports_source_en", "Source of the export figures (English)", "Source: Japan Customs, Ministry of Finance"),
    ("sources_ar", "Sources line shown under the numbers (Arabic)",
     "المصادر: مكتب الإحصاء الياباني، هيئة المعلومات الجغرافية اليابانية"),
    ("sources_en", "Sources line (English)", "Sources: Statistics Bureau of Japan; Geospatial Information Authority of Japan"),
    ("map_labels", "Seas/places to label on the map:  name@lat,lon | name@lat,lon",
     "بحر اليابان@40.5,134.5|المحيط الهادئ@30.5,147.5|بحر الصين الشرقي@29.5,125.5"),
    ("fact1_ar", "Fact 1 in Arabic. Put *stars* around words to colour them yellow", "تتكون من *14,125 جزيرة*"),
    ("fact1_en", "Fact 1 in English", "Made up of 14,125 islands"),
    ("fact1_map", "Where fact 1 shows on the map:  *  = whole country,  or  label@lat,lon[@icon] | ...", "*"),
    ("fact2_ar", "Fact 2 in Arabic", "أعلى قمة فيها *جبل فوجي* بارتفاع *3,776 متراً*"),
    ("fact2_en", "Fact 2 in English", "Its highest peak is Mount Fuji, 3,776 m high"),
    ("fact2_map", "Map anchor for fact 2 (icons: mountain, building-community, ...)", "جبل فوجي@35.36,138.73@mountain"),
    ("fact3_ar", "Fact 3 in Arabic", "لليابان *4 جزر رئيسية*"),
    ("fact3_en", "Fact 3 in English", "Japan has 4 main islands"),
    ("fact3_map", "Map anchor for fact 3", "هوكايدو@43.4,142.8|هونشو@36.4,138.6|شيكوكو@33.75,133.4|كيوشو@32.7,130.9"),
]

# Areas used for the size comparisons. Verified rows carry their source; the rest are pre-filled
# from the world-countries dataset and should be checked before a country is used in a comparison.
VERIFIED = {
    "JPN": (377980, "Geospatial Information Authority of Japan, 1 Jul 2025 (377,980.29 km²)"),
    "DEU": (357683, "Destatis, Germany, 31 Dec 2024"),
    "EGY": (1002000, "Egypt official approximate figure (about 1,002,000 km²); international sources: 1,001,450-1,002,450"),
    "SAU": (2000000, "Saudi official approximate figure (about 2 million km², Saudipedia); international sources: 2,149,690"),
    "ARE": (83600, "Widely cited figure (approx. 83,600 km²); please confirm against an official UAE source"),
}

# Reference cities for the distance section (city-centre coordinates). Add more rows as needed.
CITIES = [
    ("Dubai", "دبي", 25.2048, 55.2708), ("Abu Dhabi", "أبوظبي", 24.4539, 54.3773),
    ("Riyadh", "الرياض", 24.7136, 46.6753), ("Doha", "الدوحة", 25.2854, 51.5310),
    ("Kuwait City", "الكويت", 29.3759, 47.9774), ("Muscat", "مسقط", 23.5880, 58.3829),
    ("Manama", "المنامة", 26.2285, 50.5860), ("Cairo", "القاهرة", 30.0444, 31.2357),
    ("Amman", "عمّان", 31.9454, 35.9284), ("Beirut", "بيروت", 33.8938, 35.5018),
    ("Baghdad", "بغداد", 33.3152, 44.3661), ("Rabat", "الرباط", 34.0209, -6.8416),
    ("Istanbul", "إسطنبول", 41.0082, 28.9784), ("London", "لندن", 51.5074, -0.1278),
    ("Paris", "باريس", 48.8566, 2.3522), ("Berlin", "برلين", 52.5200, 13.4050),
    ("Rome", "روما", 41.9028, 12.4964), ("Madrid", "مدريد", 40.4168, -3.7038),
    ("Moscow", "موسكو", 55.7558, 37.6173), ("New York", "نيويورك", 40.7128, -74.0060),
    ("Washington", "واشنطن", 38.9072, -77.0369), ("Beijing", "بكين", 39.9042, 116.4074),
    ("Tokyo", "طوكيو", 35.6762, 139.6503), ("New Delhi", "نيودلهي", 28.6139, 77.2090),
    ("Sydney", "سيدني", -33.8688, 151.2093), ("Rio de Janeiro", "ريو دي جانيرو", -22.9068, -43.1729),
    ("Cape Town", "كيب تاون", -33.9249, 18.4241), ("Singapore", "سنغافورة", 1.3521, 103.8198),
]

HEAD = PatternFill("solid", fgColor="1F3A5F")
HFONT = Font(bold=True, color="FFFFFF")
VER = PatternFill("solid", fgColor="E2F5E9")


def make_template(OUT):
    wb = Workbook()
    ws = wb.active
    ws.title = "countries"
    ws.sheet_view.rightToLeft = False
    for j, (name, _, example) in enumerate(COLUMNS, start=1):
        c = ws.cell(row=1, column=j, value=name)
        c.fill, c.font = HEAD, HFONT
        ws.cell(row=2, column=j, value=example)
        ws.column_dimensions[get_column_letter(j)].width = 24 if j > 1 else 14
    ws.freeze_panes = "B2"
    for j, (name, _, _) in enumerate(COLUMNS, start=1):
        if name in ("area_km2", "population"):
            ws.cell(row=2, column=j).number_format = "#,##0"

    g = wb.create_sheet("guide")
    g.append(["column", "what to type", "example"])
    for c in g[1]:
        c.fill, c.font = HEAD, HFONT
    for name, desc, ex in COLUMNS:
        g.append([name, desc, ex])
    g.append([])
    g.append(["notes", "One row = one video. Numbers are shown with English digits. Coloured words: wrap them in *stars*.", ""])
    g.append(["", "Comparison areas come from the 'areas' sheet. Green rows there are verified; check any other row before using it.", ""])
    g.append(["", "In Video Studio: tab 🌍 Know a Country → upload this file → pick a country (or All rows) → Render.", ""])
    g.column_dimensions["A"].width, g.column_dimensions["B"].width, g.column_dimensions["C"].width = 20, 90, 60
    for row in g.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    ci = wb.create_sheet("cities")
    ci.append(["name_en", "name_ar", "lat", "lon"])
    for c in ci[1]:
        c.fill, c.font = HEAD, HFONT
    for row in CITIES:
        ci.append(list(row))
    for col, w in zip("ABCD", (18, 18, 10, 10)):
        ci.column_dimensions[col].width = w

    a = wb.create_sheet("areas")
    a.append(["cca3", "name_en", "name_ar", "area_km2", "source"])
    for c in a[1]:
        c.fill, c.font = HEAD, HFONT
    countries = json.load(open(os.path.join(HERE, "data", "countries.json"), encoding="utf-8"))
    for c in sorted(countries, key=lambda c: c["name"]["common"]):
        area, src = VERIFIED.get(c["cca3"], (c["area"], "world-countries dataset - not yet verified"))
        a.append([c["cca3"], c["name"]["common"], c["translations"]["ara"]["common"], area, src])
        if c["cca3"] in VERIFIED:
            for cell in a[a.max_row]:
                cell.fill = VER
        a.cell(row=a.max_row, column=4).number_format = "#,##0"
    for col, w in zip("ABCDE", (8, 30, 24, 14, 90)):
        a.column_dimensions[col].width = w
    a.freeze_panes = "A2"
    wb.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    make_template(os.path.join(HERE, "..", "..", "projects", "know_country_template.xlsx"))
