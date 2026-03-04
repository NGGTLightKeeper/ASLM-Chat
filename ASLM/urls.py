import time
import threading
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


# PRINT SERVER DATA
def print_server_data():
    time.sleep(1.0)

    from Settings.console import PrintTechData
    PrintTechData().PTD_Print()
threading.Thread(target=print_server_data).start()


urlpatterns = [
    path('admin/', admin.site.urls),

    path('', include('Apps.UI.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
