import argparse
import getpass
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://localhost:8000"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".config", "carcli", "token")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def save_token(token):
    os.makedirs(os.path.dirname(TOKEN_FILE), mode=0o700, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)


def load_token():
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        raise SystemExit("Not logged in. Run: carcli.py login <username>")


def delete_token():
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass


class Client:
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method, path, params=None, json_body=None, data=None, content_type=None, raw=False):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if json_body is not None:
            data = json.dumps(json_body).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                return body if raw else json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                message = json.loads(body).get("detail", body.decode())
            except ValueError:
                message = body.decode(errors="replace")
            raise ApiError(exc.code, message)
        except urllib.error.URLError as exc:
            raise SystemExit(f"Cannot reach {self.base_url}: {exc.reason}")


def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def cmd_login(client, args):
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else getpass.getpass("Password: ")
    result = client.request("POST", "/login", json_body={"username": args.username, "password": password})
    save_token(result["access_token"])
    print(f"Logged in as {args.username}. Token expires in {result['expires_in'] // 60} minutes.")


def cmd_logout(client, args):
    delete_token()
    print("Logged out.")


def cmd_whoami(client, args):
    print_json(client.request("GET", "/me"))


def cmd_cars_list(client, args):
    params = {"make": args.make} if args.make else None
    print_json(client.request("GET", "/cars", params=params))


def cmd_cars_create(client, args):
    body = {
        "make": args.make,
        "model": args.model,
        "year": args.year,
        "mileage": args.mileage,
        "description": args.description,
    }
    print_json(client.request("POST", "/cars", json_body=body))


def cmd_cars_show(client, args):
    print_json(client.request("GET", f"/cars/{args.car_id}"))


def cmd_images_upload(client, args):
    content_type = mimetypes.guess_type(args.file)[0]
    if content_type not in ("image/jpeg", "image/png"):
        raise SystemExit("Only .jpg, .jpeg and .png files are supported")
    with open(args.file, "rb") as f:
        data = f.read()
    print_json(client.request("POST", f"/cars/{args.car_id}/images", data=data, content_type=content_type))


def cmd_images_download(client, args):
    data = client.request("GET", f"/cars/{args.car_id}/images/{args.image_id}", raw=True)
    with open(args.output, "wb") as f:
        f.write(data)
    print(f"Saved {len(data)} bytes to {args.output}")


def cmd_valuations_create(client, args):
    body = {"price": args.price, "comment": args.comment}
    print_json(client.request("POST", f"/cars/{args.car_id}/valuations", json_body=body))


def cmd_valuations_list(client, args):
    print_json(client.request("GET", f"/cars/{args.car_id}/valuations"))


def cmd_reports_request(client, args):
    print_json(client.request("POST", f"/cars/{args.car_id}/reports"))


def cmd_reports_list(client, args):
    print_json(client.request("GET", f"/cars/{args.car_id}/reports"))


def cmd_reports_show(client, args):
    report = client.request("GET", f"/reports/{args.report_id}")
    if args.json:
        print_json(report)
    else:
        print(report["content"], end="")


def build_parser():
    parser = argparse.ArgumentParser(prog="carcli.py", description="CLI client for the car valuation service")
    parser.add_argument("--url", default=os.environ.get("CARCLI_URL", DEFAULT_URL), help="gateway URL")
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="log in and store the access token")
    login.add_argument("username")
    login.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    login.set_defaults(func=cmd_login, auth=False)

    commands.add_parser("logout", help="delete the stored token").set_defaults(func=cmd_logout, auth=False)
    commands.add_parser("whoami", help="show the logged-in user").set_defaults(func=cmd_whoami, auth=True)

    cars = commands.add_parser("cars", help="cars (FR2, FR3, FR4)").add_subparsers(dest="action", required=True)
    cars_list = cars.add_parser("list", help="list own cars (seller) or all cars (dealer)")
    cars_list.add_argument("--make")
    cars_list.set_defaults(func=cmd_cars_list, auth=True)
    cars_create = cars.add_parser("create", help="submit a car (seller)")
    cars_create.add_argument("--make", required=True)
    cars_create.add_argument("--model", required=True)
    cars_create.add_argument("--year", type=int, required=True)
    cars_create.add_argument("--mileage", type=int, required=True)
    cars_create.add_argument("--description", default="")
    cars_create.set_defaults(func=cmd_cars_create, auth=True)
    cars_show = cars.add_parser("show", help="show one car")
    cars_show.add_argument("car_id", type=int)
    cars_show.set_defaults(func=cmd_cars_show, auth=True)

    images = commands.add_parser("images", help="car images (FR2)").add_subparsers(dest="action", required=True)
    images_upload = images.add_parser("upload", help="upload a JPEG or PNG image (seller)")
    images_upload.add_argument("car_id", type=int)
    images_upload.add_argument("file")
    images_upload.set_defaults(func=cmd_images_upload, auth=True)
    images_download = images.add_parser("download", help="download an image")
    images_download.add_argument("car_id", type=int)
    images_download.add_argument("image_id")
    images_download.add_argument("output")
    images_download.set_defaults(func=cmd_images_download, auth=True)

    valuations = commands.add_parser("valuations", help="valuations (FR5)").add_subparsers(dest="action", required=True)
    valuations_create = valuations.add_parser("create", help="create a valuation (dealer)")
    valuations_create.add_argument("car_id", type=int)
    valuations_create.add_argument("--price", type=int, required=True)
    valuations_create.add_argument("--comment", default="")
    valuations_create.set_defaults(func=cmd_valuations_create, auth=True)
    valuations_list = valuations.add_parser("list", help="list valuations for a car")
    valuations_list.add_argument("car_id", type=int)
    valuations_list.set_defaults(func=cmd_valuations_list, auth=True)

    reports = commands.add_parser("reports", help="valuation reports (FR6)").add_subparsers(dest="action", required=True)
    reports_request = reports.add_parser("request", help="request a report for own car (seller)")
    reports_request.add_argument("car_id", type=int)
    reports_request.set_defaults(func=cmd_reports_request, auth=True)
    reports_list = reports.add_parser("list", help="list reports for own car (seller)")
    reports_list.add_argument("car_id", type=int)
    reports_list.set_defaults(func=cmd_reports_list, auth=True)
    reports_show = reports.add_parser("show", help="show a report (seller)")
    reports_show.add_argument("report_id", type=int)
    reports_show.add_argument("--json", action="store_true")
    reports_show.set_defaults(func=cmd_reports_show, auth=True)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = Client(args.url, token=load_token() if args.auth else None)
    try:
        args.func(client, args)
    except ApiError as exc:
        if exc.status == 401 and args.auth:
            print("Session expired or invalid. Log in again.", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
