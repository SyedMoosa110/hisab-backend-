from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        import os
        import base64
        
        # Base64 encode the logo and write to LogoConstant.js
        try:
            logo_path = r"C:\Users\Moosa\.gemini\antigravity-ide\brain\805f7d8f-3e90-4b24-ba21-ce0bc0f41f29\media__1784112752945.png"
            if os.path.exists(logo_path):
                with open(logo_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                
                js_content = f'export const CGPLUX_LOGO = "data:image/png;base64,{encoded_string}";\n'
                dest_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "src", "LogoConstant.js")
                
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(js_content)
                print(f"--- Successfully generated LogoConstant.js at {dest_path} ---")
        except Exception as e:
            print(f"Failed to generate LogoConstant.js: {e}")

        # Only run in the active process (not the loader) to avoid double execution
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from django.core.management import call_command
                print("--- Automatically generating migrations ---")
                call_command('makemigrations', 'accounts')
                print("--- Automatically applying migrations ---")
                call_command('migrate')
                print("--- Migrations completed successfully! ---")
            except Exception as e:
                print(f"Auto-migration failed: {e}")
