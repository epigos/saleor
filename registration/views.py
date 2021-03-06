from urllib import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (login as auth_login, logout as auth_logout,
                                 get_user_model)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (login as django_login_view,
                                       password_change)
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from .forms import (
    RegisterOrResetPasswordForm,
    RequestEmailChangeForm,
    RequestEmailConfirmationForm,
    LoginForm,
    OAuth2CallbackForm)
from .models import EmailConfirmationRequest, EmailChangeRequest
from .utils import (
    get_facebook_login_url,
    get_google_login_url,
    get_local_host,
    url)

User = get_user_model()
now = timezone.now


def login(request):
    local_host = get_local_host(request)
    ctx = {'facebook_login_url': get_facebook_login_url(local_host),
           'google_login_url': get_google_login_url(local_host)}
    return django_login_view(request, authentication_form=LoginForm,
                             extra_context=ctx)


def logout(request):
    auth_logout(request)
    messages.success(request, _('You have been successfully logged out.'))
    return redirect(settings.LOGIN_REDIRECT_URL)


def oauth_callback(request, service):
    local_host = get_local_host(request)
    form = OAuth2CallbackForm(service=service, local_host=local_host,
                              data=request.GET)
    if form.is_valid():
        try:
            user = form.get_authenticated_user()
            return _login_user(request, user)
        except ValueError, e:
            messages.error(request, unicode(e))
    else:
        for _field, errors in form.errors.items():
            for error in errors:
                messages.error(request, error)
    return redirect('registration:login')


def request_email_confirmation(request):
    local_host = get_local_host(request)
    if request.method == 'POST':
        form = RequestEmailConfirmationForm(local_host=local_host,
                                            data=request.POST)
        if form.is_valid():
            form.send()
            msg = _('Confirmation email has been sent. '
                    'Please check your inbox.')
            messages.success(request, msg)
            return redirect(settings.LOGIN_REDIRECT_URL)
    else:
        form = RequestEmailConfirmationForm(local_host=local_host)

    return TemplateResponse(request,
                            'registration/request_email_confirmation.html',
                            {'form': form})


@login_required
def request_email_change(request):
    if request.method == 'POST':
        form = RequestEmailChangeForm(local_host=get_local_host(request),
                                      user=request.user, data=request.POST)
        if form.is_valid():
            form.send()
            msg = _('Confirmation email has been sent. '
                    'Please check your inbox.')
            messages.success(request, msg)
            return redirect(settings.LOGIN_REDIRECT_URL)
    else:
        form = RequestEmailChangeForm()

    return TemplateResponse(request,
                            'registration/request_email_confirmation.html',
                            {'form': form})


def confirm_email(request, token):
    try:
        email_confirmation_request = EmailConfirmationRequest.objects.get(
            token=token, valid_until__gte=now())
        # TODO: cronjob (celery task) to delete stale tokens
    except EmailConfirmationRequest.DoesNotExist:
        return TemplateResponse(request, 'registration/invalid_token.html')

    if request.method == 'POST':
        form = RegisterOrResetPasswordForm(
            email_confirmation_request=email_confirmation_request,
            data=request.POST)
        if form.is_valid():
            user = form.get_authenticated_user()
            return _login_user(request, user)
    else:
        form = RegisterOrResetPasswordForm(
            email_confirmation_request=email_confirmation_request)

    return TemplateResponse(
        request, 'registration/set_password.html', {'form': form})


def change_email(request, token):
    try:
        email_change_request = EmailChangeRequest.objects.get(
            token=token, valid_until__gte=now())
            # TODO: cronjob (celery task) to delete stale tokens
    except EmailChangeRequest.DoesNotExist:
        return TemplateResponse(request, 'registration/invalid_token.html')

    # if another user is logged in, we need to log him out, to allow the email
    # owner confirm his identity
    if request.user != email_change_request.user:
        auth_logout(request)
    if not request.user.is_authenticated():
        query = urlencode({
            'next': request.get_full_path(),
            'email': email_change_request.user.email})
        login_url = url(path=settings.LOGIN_URL, query=query)
        return redirect(login_url)

    request.user.email = email_change_request.email
    request.user.save()
    email_change_request.delete()

    messages.success(request, _('Your email has been successfully changed'))
    return redirect(settings.LOGIN_REDIRECT_URL)


def _login_user(request, user):
    auth_login(request, user)
    msg = _('You have been successfully logged in.')
    messages.success(request, msg)
    return redirect(settings.LOGIN_REDIRECT_URL)


def change_password(request):
    return password_change(
        request, template_name='registration/change_password.html',
        post_change_redirect=reverse('profile:details')
    )
