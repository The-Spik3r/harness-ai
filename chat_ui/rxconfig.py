import reflex as rx

config = rx.Config(
    show_built_with_reflex=False,
    app_name="chat_ui",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(),
    ]
)