"""
URL configuration for shenzhen project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from django.urls import include
from django.views.generic import RedirectView

from main import views as main_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", include("login.urls")),
    path("", RedirectView.as_view(pattern_name="login")),
    path("main/", main_views.index, name="main"),
    path("agenda/", include("main.urls")),
    path("braga/", include("braga.urls")),
    path("fucador/", include("fucador.urls")),
    path("news/", include("news_.urls")),
]
