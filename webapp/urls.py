from django.urls import path
from . import views

urlpatterns = [
    path('', views.index),
    path('api/examples/', views.examples),
    path('api/examples/<str:name>/', views.example),
    path('api/graph/validate/', views.validate),
    path('api/run/', views.run),
]

handler404 = views.not_found
handler500 = views.server_error
