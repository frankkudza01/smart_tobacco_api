from django.urls import path

from apps.accounts.views import UserCreateView, UserDetailView, UserListView

urlpatterns = [
    path("", UserListView.as_view(), name="user-list"),
    path("create/", UserCreateView.as_view(), name="user-create"),
    path("<uuid:pk>/", UserDetailView.as_view(), name="user-detail"),
]
