"""One self-contained executable for both service control and the HTTP service."""
import sys

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'serve':
        sys.argv.pop(1)
        import server
        server.main()
    else:
        import manage
        manage.main()
