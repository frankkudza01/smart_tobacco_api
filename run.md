cd backend
cp .env.example .env
docker-compose up --build
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py seed_data