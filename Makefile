RUN_IN_VENV=./scripts/run_in_venv.sh

.PHONY: refresh bulk-load run-gpt tests

refresh:
	$(RUN_IN_VENV) spotify_automation/daily_dj_refresh.py

bulk-load:
	$(RUN_IN_VENV) spotify_automation/bulk_load_tracks.py

run-gpt:
	$(RUN_IN_VENV) spotify_automation/run_gpt_recommender.py

tests:
	$(RUN_IN_VENV) -m unittest discover -s tests
