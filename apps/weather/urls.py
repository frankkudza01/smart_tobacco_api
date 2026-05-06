from django.urls import path

from apps.weather.views import ZimbabweWeatherForecastView, ZimbabweWeatherRegionsView

urlpatterns = [
    path("zimbabwe/regions/", ZimbabweWeatherRegionsView.as_view(), name="weather-zw-regions"),
    path("zimbabwe/forecast/", ZimbabweWeatherForecastView.as_view(), name="weather-zw-forecast"),
]
