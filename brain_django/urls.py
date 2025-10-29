"""
URL configuration for brain_django project.

The urlpatterns list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
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
 
from django.urls import path, re_path,include
from django.contrib import admin
from django.conf import settings
from brain_start.views import runoob, serve_report, import_eeg_data,analyze_existing_data,test_api_key
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', runoob),
    path('api/import-eeg-data/', import_eeg_data, name='import_eeg_data'),
    path('api/analyze-existing-data/', analyze_existing_data, name='analyze_existing_data'),
    path('api/test-api-key/', test_api_key, name='test_api_key'),
    re_path(r'^reports/(?P<filename>[^/]+)$', serve_report, name='serve_report'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None)