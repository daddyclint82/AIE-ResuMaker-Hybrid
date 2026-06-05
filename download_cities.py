import json
import urllib.request
import ijson
import os

# Download and parse the cities database
url = "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database/master/json/countries%2Bstates%2Bcities.json"
output_file = "cities.json"

print("Downloading cities database...")

us_states = {}
us_cities_by_state = {}

try:
    # Stream parse the large JSON file
    with urllib.request.urlopen(url) as response:
        for country in ijson.items(response, 'item'):
            if country.get('iso2') == 'US':
                for state in country.get('states', []):
                    state_code = state['state_code']
                    state_name = state['name']
                    us_states[state_code] = state_name
                    
                    cities = []
                    for city in state.get('cities', []):
                        cities.append(city['name'])
                    
                    us_cities_by_state[state_code] = sorted(cities)
                break
    
    # Save to file
    data = {
        "states": us_states,
        "cities_by_state": us_cities_by_state
    }
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    total_cities = sum(len(cities) for cities in us_cities_by_state.values())
    print(f"✓ Downloaded {len(us_states)} states")
    print(f"✓ Total cities: {total_cities}")
    print(f"✓ Saved to {output_file}")
    
    # Show sample
    print("\nSample states:")
    for code in ['TX', 'CA', 'NY', 'FL', 'IL']:
        if code in us_cities_by_state:
            count = len(us_cities_by_state[code])
            print(f"  {code}: {count} cities")
    
    # Show Texas samples
    print("\nTexas cities sample:")
    for city in us_cities_by_state.get('TX', [])[:10]:
        print(f"  {city}")

except Exception as e:
    print(f"Error: {e}")
    # Fallback: create minimal dataset
    fallback_data = {
        "states": {
            "TX": "Texas",
            "CA": "California", 
            "NY": "New York",
            "FL": "Florida",
            "IL": "Illinois",
            "PA": "Pennsylvania",
            "OH": "Ohio",
            "GA": "Georgia",
            "NC": "North Carolina",
            "MI": "Michigan"
        },
        "cities_by_state": {
            "TX": ["Houston", "Dallas", "San Antonio", "Austin", "Fort Worth", "El Paso", "Arlington", "Corpus Christi", "Plano", "Laredo", "Lubbock", "Garland", "Irving", "Amarillo", "Grand Prairie", "Brownsville", "McKinney", "Frisco", "Pasadena", "Mesquite", "Killeen", "McAllen", "Waco", "Denton", "Midland", "Carrollton", "Round Rock", "Abilene", "Pearland", "Richardson", "Odessa", "Beaumont", "The Woodlands", "College Station", "Lewisville", "Tyler", "League City", "Wichita Falls", "Allen", "San Angelo", "Edinburg", "Conroe", "Bryan", "Mission", "Longview", "Pharr", "Baytown", "Flower Mound", "Missouri City", "Temple"],
            "CA": ["Los Angeles", "San Diego", "San Jose", "San Francisco", "Fresno", "Sacramento", "Long Beach", "Oakland", "Bakersfield", "Anaheim", "Santa Ana", "Riverside", "Stockton", "Chula Vista", "Irvine", "Fremont", "San Bernardino", "Modesto", "Oxnard", "Fontana"],
            "NY": ["New York City", "Buffalo", "Rochester", "Yonkers", "Syracuse", "Albany", "New Rochelle", "Mount Vernon", "Schenectady", "Utica", "White Plains", "Hempstead", "Troy", "Niagara Falls", "Binghamton", "Freeport", "Valley Stream", "Long Beach", "Rome", "North Tonawanda"]
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(fallback_data, f, indent=2)
    
    print(f"✓ Created fallback dataset with {len(fallback_data['states'])} states")
