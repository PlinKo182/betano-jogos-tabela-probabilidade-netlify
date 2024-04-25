from fastapi import FastAPI, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import requests
from datetime import datetime
import re
import simplejson as json
from typing import List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

app = FastAPI()


class TeamGamesResponse(BaseModel):
    matches: List[dict]
    standings: List[dict]
    probability: List[dict]


@app.get("/", include_in_schema=False)
def docs_redirect():
    return RedirectResponse(url="/docs")


@app.get("/get_team_games", response_model=TeamGamesResponse)
async def get_team_games(
        team_name: str = Query(..., title="Nome da Equipa", description="Nome da equipa")
):
    logging.info(f"Fetching team games for: {team_name}")

    # List of URLs
    urls = [
        "https://stats.fn.sportradar.com/betano/pt/Europe:London/gismo/stats_season_fixtures2/106501",
        "https://stats.fn.sportradar.com/betano/pt/Europe:London/gismo/stats_season_fixtures2/106509",
        "https://stats.fn.sportradar.com/betano/pt/Europe:London/gismo/stats_season_fixtures2/105353",
        "https://stats.fn.sportradar.com/betano/pt/Europe:London/gismo/stats_season_fixtures2/106499",
        "https://stats.fn.sportradar.com/betano/pt/Europe:London/gismo/stats_season_fixtures2/105937",
        "https://stats.fn.sportradar.com/betano/pt/Europe:London/gismo/stats_season_fixtures2/107373"
    ]

    # Headers to simulate a browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }

    # Lists to store data
    all_team_games = []
    all_standings = []
    probability = []  # Inicializando a variável como uma lista vazia

    # Initialize last_unplayed_game_id
    last_unplayed_game_id = None

    # Loop through each URL
    for url in urls:
        logging.info(f"Fetching data from URL: {url}")

        # Make the request
        response = requests.get(url, headers=headers)

        # Check response status
        if response.status_code != 200:
            logging.error(f"Failed to fetch data from URL: {url}")
            continue

        # Extract the ID of the season from the URL
        season_id = url.split("/")[-1]

        # Check if the team is involved in the current season
        if not team_name_in_season(url, team_name, headers):
            logging.info(f"Team '{team_name}' is not involved in season with ID: {season_id}")
            continue

        # Build the URL for the season tables using the season ID
        season_tables_url = f"https://stats.fn.sportradar.com/betano/pt/Europe:London/gismo/stats_season_tables/{season_id}"

        # Make the request to the season tables URL and process the data as needed
        standings_response = requests.get(season_tables_url, headers=headers)

        if standings_response.status_code != 200:
            logging.error(f"Failed to fetch standings data for season with ID: {season_id}")
            continue

        standings_data = standings_response.json()
        standings_table = standings_data['doc'][0]['data']['tables'][0]['tablerows']

        # Extract data from the standings table
        for standing_row in standings_table:
            position = standing_row["pos"]
            standing_team_name = standing_row["team"]["mediumname"]
            games_played = standing_row["total"]
            points = standing_row["pointsTotal"]
            draws = standing_row["drawTotal"]

            standings_info = {
                "Posição": position,
                "Nome": standing_team_name,
                "Jogos": games_played,
                "Pontos": points,
                "Empates": draws,
            }
            all_standings.append(standings_info)

        # Make the request to the matches URL and process the data as needed
        matches_response = requests.get(url, headers=headers)

        if matches_response.status_code != 200:
            logging.error(f"Failed to fetch matches data from URL: {url}")
            continue

        matches_data = matches_response.json()['doc'][0]['data']['matches']

        # Iterate over each match and extract the necessary data
        for match_data in matches_data:
            # Use the actual match ID from the API response
            match_id = match_data["_id"]
            home_team = match_data['teams']['home']['mediumname']
            away_team = match_data['teams']['away']['mediumname']
            home_score = match_data['result']['home'] if 'result' in match_data else None
            away_score = match_data['result']['away'] if 'result' in match_data else None
            match_date = match_data['time']['date']
            match_time = match_data['time']['time']
            match_status = match_data['status']
            match_round_data = match_data.get('roundname', {})
            match_round = match_round_data.get('name', None)

            # Replace 'Placar Casa' with 'ADI' if status is 'Adiado'
            if match_status == 'Adiado':
                resultado = 'ADI'
            else:
                resultado = f"{home_score} : {away_score}" if home_score is not None and away_score is not None else '-:-'

            # Modify the date format to the correct format
            try:
                match_date_formatted = datetime.strptime(match_date, "%d/%m/%y").strftime("%d/%m/%Y")
            except ValueError:
                match_date_formatted = match_data['time']['date']

            # Add match data to the list if the team is involved
            if team_name in [home_team, away_team]:
                match = {
                    "_id": match_id,
                    "Jornada": match_round,
                    "Data": match_date_formatted,
                    "Hora": match_time,
                    "Equipa_da_casa": home_team,
                    "Resultado": resultado,
                    "Equipa_visitante": away_team
                }
                all_team_games.append(match)

                # Se o resultado for "-:-", atualize last_unplayed_game_id
                if resultado == "-:-" and last_unplayed_game_id is None:
                    last_unplayed_game_id = match_id

                    # Agora, vamos lidar com a segunda parte do código que busca last_unplayed_game_id
                    # URL do site
                    last_unplayed_game_url = f"https://s5.sir.sportradar.com/betano/pt/1/season/{season_id}/headtohead/match/{last_unplayed_game_id}"

                    # Faz a requisição ao site
                    response = requests.get(last_unplayed_game_url, headers=headers)

                    # Encontrar a parte do script que contém 'probabilities' e 'teams' usando expressões regulares
                    match_probabilities = re.search(r'"probabilities":\s*({.*?})', response.text)
                    match_teams = re.search(r'"teams":\s*({.*?}})', response.text)

                    if match_probabilities and match_teams:
                        probabilities_json = match_probabilities.group(1)
                        teams_json = match_teams.group(1)

                        # Utilizando simplejson para decodificar os JSONs
                        probabilities_data = json.loads(probabilities_json)
                        teams_data = json.loads(teams_json)

                        # Extrair informações específicas
                        home_team = teams_data['home']['mediumname']
                        away_team = teams_data['away']['mediumname']
                        probability_home = probabilities_data['home']
                        probability_away = probabilities_data['away']
                        probability_draw = probabilities_data['draw']

                        # Encontrar a parte do script que contém 'data' dentro de 'match' usando expressões regulares
                        match_data = re.search(r'"data":\s*{"match":\s*({.*?})}', response.text)

                        if match_data:
                            data_content = match_data.group(1)

                            # Procurar por "date" dentro do conteúdo de "data"
                            match_date = re.search(r'"date":\s*"([^"]+)"', data_content)

                            if match_date:
                                date_value = match_date.group(1)

                                # Arredondar a probabilidade para zero casas decimais
                                probability_draw_rounded = round(probability_draw)

                                # Adicionar as informações à lista de probability como um dicionário
                                probability.append({
                                    "Data": date_value,
                                    "Equipa_da_casa": home_team,
                                    "Equipa_visitante": away_team,
                                    "Probabilidade": probability_draw_rounded
                                })

    # Retornar TeamGamesResponse com probability como uma lista de dicionários
    return TeamGamesResponse(matches=all_team_games, standings=all_standings, probability=probability)


def team_name_in_season(url: str, team_name: str, headers: dict) -> bool:
    # Make the HTTP request with the header
    response = requests.get(url, headers=headers)

    # Check if the request was successful
    if response.status_code != 200:
        logging.error(f"Failed to fetch data from URL: {url}")
        return False

    # Convert JSON data to a Python dictionary
    data = response.json()

    # Extract relevant data from the data structure
    matches_data = data['doc'][0]['data']['matches']

    # Iterate over each match and check if the team is involved
    for match_data in matches_data:
        home_team = match_data['teams']['home']['mediumname']
        away_team = match_data['teams']['away']['mediumname']

        if team_name in [home_team, away_team]:
            return True

    return False
