from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("profile/qr/", views.create_qr, name="create-qr"),
    path("staff/scanner/", views.scanner, name="scanner"),
    path("staff/display/", views.display, name="display"),
    path("staff/scan/", views.scan_qr, name="scan-qr"),
    path("staff/display/latest/", views.latest_checkin, name="latest-checkin"),
    path("staff/", views.staff_dashboard, name="staff-dashboard"),
    path("staff/members/add/", views.member_create, name="staff-member-create"),
    path("staff/members/<int:pk>/", views.member_detail, name="staff-member-detail"),
    path("staff/members/<int:pk>/edit/", views.member_edit, name="staff-member-edit"),
    path("staff/members/<int:pk>/delete/", views.member_delete, name="staff-member-delete"),
    path("staff/members/<int:pk>/checkin/", views.member_manual_checkin, name="staff-member-checkin"),
    path("staff/members/<int:member_pk>/memberships/add/", views.membership_create, name="staff-membership-create"),
    path("staff/memberships/<int:pk>/edit/", views.membership_edit, name="staff-membership-edit"),
    path("staff/memberships/<int:pk>/delete/", views.membership_delete, name="staff-membership-delete"),
    path("staff/packages/", views.package_list, name="staff-packages"),
    path("staff/packages/add/", views.package_create, name="staff-package-create"),
    path("staff/packages/<int:pk>/edit/", views.package_edit, name="staff-package-edit"),
    path("staff/packages/<int:pk>/delete/", views.package_delete, name="staff-package-delete"),
]