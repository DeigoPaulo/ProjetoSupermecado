from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from .forms import UsuarioPerfilForm
from .permissions import SISTEMA, RoleRequiredMixin, role_required


class UsuarioListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    required_roles = SISTEMA
    model = User
    template_name = "accounts/usuario_list.html"
    context_object_name = "usuarios"
    paginate_by = 30

    def get_queryset(self):
        queryset = User.objects.select_related("perfil_supermercado", "perfil_supermercado__filial").order_by("username")
        termo = self.request.GET.get("q")
        if termo:
            queryset = queryset.filter(username__icontains=termo) | queryset.filter(first_name__icontains=termo) | queryset.filter(email__icontains=termo)
        return queryset


@login_required
@role_required(*SISTEMA)
def usuario_form(request, pk=None):
    usuario = get_object_or_404(User, pk=pk) if pk else None
    if request.method == "POST":
        form = UsuarioPerfilForm(request.POST, instance=usuario)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Usuario salvo com sucesso.")
            return redirect("accounts:usuario_editar", pk=user.pk)
    else:
        form = UsuarioPerfilForm(instance=usuario)

    return render(request, "accounts/usuario_form.html", {"form": form, "usuario_obj": usuario})
