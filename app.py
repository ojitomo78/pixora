import flet as ft
from src.controllers.auth_controller import AuthController
from src.controllers.feed_controller import FeedController
from src.controllers.recommendation_controller import RecommendationController
from src.views.login_view import LoginView
from src.views.feed_view import FeedView
from src.views.explore_view import ExploreView
from src.services.api_client import ApiClient

def main(page: ft.Page):
    page.title = "Pixora - Red Social de Fotografía"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    
    page.window.width = 460
    page.window.height = 800
    page.window.min_width = 380
    page.window.min_height = 600

    api_client = ApiClient()
    auth_controller = AuthController(api_client)
    feed_controller = FeedController(api_client)
    rec_controller = RecommendationController(api_client)

    def show_main_app():
        page.clean()
        username = auth_controller.current_username or "usuario"

        feed_view = FeedView(username, feed_controller, on_logout=show_login)
        explore_view = ExploreView(rec_controller)

        body_container = ft.Container(content=feed_view, expand=True, padding=10)

        def on_nav_change(e):
            selected_idx = e.control.selected_index
            if selected_idx == 0:
                body_container.content = feed_view
            elif selected_idx == 1:
                body_container.content = explore_view
            page.update()

        nav_bar = ft.NavigationBar(
            selected_index=0,
            on_change=on_nav_change,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.DYNAMIC_FEED, label="Feed"),
                ft.NavigationBarDestination(icon=ft.Icons.EXPLORE, label="Poses y Lugares"),
            ]
        )

        page.add(
            ft.Column([
                body_container,
                nav_bar
            ], expand=True, spacing=0)
        )
        page.run_task(feed_view.load_feed)

    def show_login():
        page.clean()
        auth_controller.logout()

        login_view = LoginView(
            auth_controller,
            on_login_success=show_main_app,
        )
        page.add(ft.Container(content=login_view, alignment=ft.Alignment(0, 0), expand=True, padding=20))

    show_login()

ft.run(main)