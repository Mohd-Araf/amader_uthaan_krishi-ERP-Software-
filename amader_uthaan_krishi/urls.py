from django.conf import settings
from django.contrib import admin
from django.urls import path, include

from . import views
from .views import home
from django.conf.urls.static import static
urlpatterns = [

    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('accounts/', include('apps.accounts.urls')),
    path('products/', include('apps.products.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
    path("finance/", include("apps.finance.urls")
),


]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)