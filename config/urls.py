"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path('', include('apps.relatorios.urls')),
    path('usuarios/', include('apps.accounts.urls')),
    path('clientes/', include('apps.clientes.urls')),
    path('fornecedores/', include('apps.fornecedores.urls')),
    path('compras/', include('apps.compras.urls')),
    path('produtos/', include('apps.produtos.urls')),
    path('estoque/', include('apps.estoque.urls')),
    path('promocoes/', include('apps.promocoes.urls')),
    path('pdv/', include('apps.pdv.urls')),
    path('financeiro/', include('apps.financeiro.urls')),
    path('fiscal/', include('apps.fiscal.urls')),
    path('pedidos-online/', include('apps.marketplace.urls')),
    path('empresas/', include('apps.empresas.urls')),
    path('configuracoes/', include('apps.configuracoes.urls')),
    path('licenciamento/', include('apps.licenciamento.urls')),
    path('auditoria/', include('apps.auditoria.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path(
        'recuperar-senha/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
        ),
        name='password_reset',
    ),
    path(
        'recuperar-senha/enviado/',
        auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'redefinir-senha/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'),
        name='password_reset_confirm',
    ),
    path(
        'redefinir-senha/concluido/',
        auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'),
        name='password_reset_complete',
    ),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
