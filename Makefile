.PHONY: install migrate run test lint seed superuser docker-up

install:
	pip install -r requirements-dev.txt

migrate:
	python manage.py makemigrations && python manage.py migrate

run:
	python manage.py runserver

test:
	pytest

lint:
	ruff check .

seed:
	python manage.py seed_demo_data

superuser:
	python manage.py createsuperuser

docker-up:
	docker compose up --build
