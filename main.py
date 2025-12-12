
import json
import random
import re
import time
from dataclasses import asdict, dataclass
from typing import List, Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# ========================
# CONFIGURACIÓN ESTÁTICA
# Completa estos valores antes de ejecutar.
# ========================
INSTA_USERNAME = "adriannole73@gmail.com"
INSTA_PASSWORD = "arbolito157"
TARGET_ACCOUNT = "esedgarcia"  # Cuenta cuyo listado de seguidos quieres extraer
OUTPUT_JSON = "seguido_detalle.json"  # Archivo de salida
MAX_PROFILES = 100  # Límite de perfiles


def build_driver() -> webdriver.Chrome:
	"""Crea el driver de Chrome con opciones que reducen la detección de automatización."""
	chrome_options = webdriver.ChromeOptions()
	chrome_options.add_argument("--disable-blink-features=AutomationControlled")
	chrome_options.add_argument("--start-maximized")
	chrome_options.add_argument("--lang=es-ES")
	chrome_options.add_argument(
		"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
	)
	chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
	chrome_options.add_experimental_option("useAutomationExtension", False)
	return webdriver.Chrome(options=chrome_options)


def human_sleep(min_s: float = 1.2, max_s: float = 3.5, label: str = "") -> None:
	"""Pausa aleatoria para simular comportamiento humano."""
	dur = random.uniform(min_s, max_s)
	if label:
		print(f" Pausa {label}: {dur:.2f}s")
	time.sleep(dur)


def wait_for(driver, locator: tuple, timeout: int = 15):
	return WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))


def safe_text(regex: str, source: str) -> Optional[str]:
	m = re.search(regex, source, flags=re.DOTALL)
	return m.group(1) if m else None


def decode_json_string(txt: Optional[str]) -> Optional[str]:
	if txt is None:
		return None
	try:
		return json.loads(f'"{txt}"')
	except Exception:
		return txt


def normalize_count(txt: str) -> Optional[int]:
	"""Convierte texto de conteo (ej: '1,234' o '1.5K' o '2M') a entero."""
	if not txt:
		return None
	# Quitar puntos y comas
	t = txt.lower().replace('.', '').replace(',', '').strip()
	mult = 1
	if t.endswith('k'):
		mult = 1000
		t = t[:-1]
	elif t.endswith('m'):
		mult = 1000000
		t = t[:-1]
	try:
		return int(float(t) * mult)
	except Exception:
		return None


@dataclass
class ProfileData:
	username: str
	nombre: Optional[str]
	biografia: Optional[str]
	tipo_cuenta: Optional[str]
	seguidores: Optional[int]
	seguidos: Optional[int]
	perfil_url: str


def login(driver: webdriver.Chrome, user: str, password: str) -> None:
	driver.get("https://www.instagram.com/accounts/login/")
	human_sleep(4, 6, label="cargar login")

	user_input = wait_for(driver, (By.NAME, "username"))
	pass_input = wait_for(driver, (By.NAME, "password"))

	user_input.send_keys(user)
	pass_input.send_keys(password)
	pass_input.send_keys(Keys.ENTER)

	try:
		WebDriverWait(driver, 20).until(lambda d: "login" not in d.current_url)
		print(" Login exitoso")
	except TimeoutException:
		raise RuntimeError("No se pudo iniciar sesión: verifica credenciales o desafíos de seguridad")


def open_following_modal(driver: webdriver.Chrome, username: str) -> None:
	driver.get(f"https://www.instagram.com/{username}/")
	human_sleep(3, 5, label="cargar perfil objetivo")

	try:
		following_link = wait_for(driver, (By.XPATH, '//a[contains(@href, "/following/")]'))
	except TimeoutException:
		raise RuntimeError("No se encontró el enlace de 'seguidos' (following)")

	following_link.click()
	human_sleep(3, 5, label="abrir modal seguidos")


def collect_following_usernames(driver: webdriver.Chrome, manual_idle_s: int = 10) -> List[str]:
	"""Extrae usernames de la lista de seguidos.

	Si se encuentra el contenedor scrollable, hace scroll automático.
	Si no, entra en modo manual: tú scrolleas y el script sigue leyendo mientras
	los usernames aumenten. Se detiene tras `manual_idle_s` segundos sin nuevos
	usuarios.
	"""
	scroll_box = None
	dialog = None
	try:
		scroll_box = driver.find_element(By.CSS_SELECTOR, "div._aano")
	except NoSuchElementException:
		try:
			scroll_box = driver.find_element(By.XPATH, '//div[@role="dialog"]//div[contains(@style, "overflow-y: scroll") or contains(@style, "overflow: auto")]')
		except NoSuchElementException:
			pass

	try:
		dialog = driver.find_element(By.XPATH, '//div[@role="dialog"]')
	except NoSuchElementException:
		dialog = None

	usernames: List[str] = []

	# MODO AUTOMÁTICO
	if scroll_box:
		last_height = 0
		no_change = 0
		max_scrolls = 60
		for i in range(max_scrolls):
			human_sleep(1.0, 2.2, label=f"scroll {i+1}")
			driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_box)
			human_sleep(1.6, 3.0, label="carga nuevos elementos")

			links = scroll_box.find_elements(By.XPATH, './/a[contains(@href, "/") and not(contains(@href, "tagged"))]')
			for link in links:
				href = link.get_attribute("href")
				if not href:
					continue
				candidate = href.rstrip("/").split("/")[-1]
				if candidate and candidate not in usernames and candidate not in {"accounts", "explore", "reels", "direct"}:
					usernames.append(candidate)

			new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_box)
			if new_height == last_height:
				no_change += 1
				if no_change >= 3:
					print(" Lista de seguidos parece completa")
					break
			else:
				no_change = 0
				last_height = new_height

		print(f"👥 Encontrados {len(usernames)} seguidos (modo automático)")
		return usernames

	# MODO MANUAL
	if not dialog:
		raise RuntimeError("No se encontró el modal de seguidos para modo manual")

	print("⚠️ No se halló contenedor scrollable. Modo manual: desplázate tú y yo leeré mientras haya nuevos usuarios.")
	last_count = 0
	last_change_ts = time.time()
	hard_timeout = 8 * 60  # límite de seguridad de 8 minutos

	while True:
		links = dialog.find_elements(By.XPATH, './/a[contains(@href, "/") and not(contains(@href, "tagged"))]')
		for link in links:
			href = link.get_attribute("href")
			if not href:
				continue
			candidate = href.rstrip("/").split("/")[-1]
			if candidate and candidate not in usernames and candidate not in {"accounts", "explore", "reels", "direct"}:
				usernames.append(candidate)

		if len(usernames) > last_count:
			last_change_ts = time.time()
			last_count = len(usernames)

		idle = time.time() - last_change_ts
		if idle >= manual_idle_s:
			print(f" Sin nuevos usuarios por {manual_idle_s}s. Deteniendo lectura manual.")
			break

		if (time.time() - last_change_ts) > hard_timeout:
			print(" Tiempo máximo alcanzado en modo manual. Deteniendo.")
			break

		human_sleep(1.0, 1.6, label="esperando scroll manual")

	print(f"👥 Encontrados {len(usernames)} seguidos (modo manual)")
	return usernames


def parse_counts(source: str) -> tuple[Optional[int], Optional[int]]:
	followers = safe_text(r'"edge_followed_by":\{"count":(\d+)\}', source)
	following = safe_text(r'"edge_follow":\{"count":(\d+)\}', source)
	return (int(followers) if followers else None, int(following) if following else None)


def parse_account_type(source: str) -> Optional[str]:
	raw = safe_text(r'"account_type":"(.*?)"', source)
	if not raw:
		return None
	raw_upper = raw.upper()
	if "PERSONAL" in raw_upper:
		return "PERSONAL"
	if "CREATOR" in raw_upper:
		return "CREATOR"
	if "BUSINESS" in raw_upper:
		return "BUSINESS"
	return raw_upper


def scrape_profile(driver: webdriver.Chrome, username: str) -> ProfileData:
	url = f"https://www.instagram.com/{username}/"
	driver.get(url)
	human_sleep(2.5, 4.5, label=f"perfil {username}")

	source = driver.page_source

	# Intentar extraer mediante XPath (DOM visible)
	full_name = None
	try:
		full_name_el = driver.find_element(By.XPATH, '//section//header//h1 | //header//h2[contains(@class, "x1lliihq")]')
		full_name = full_name_el.text.strip() or None
	except NoSuchElementException:
		pass

	# Fallback regex si XPath falla
	if not full_name:
		full_name_raw = safe_text(r'"full_name":"(.*?)"', source)
		full_name = decode_json_string(full_name_raw)

	# Biografía mediante XPath (múltiples estrategias) - EVITANDO el nombre
	biografia = None
	try:
		# Estrategia 1: XPath absoluto del inspector
		bio_el = driver.find_element(By.XPATH, '/html/body/div[1]/div/div/div[2]/div/div/div[1]/div[2]/div[1]/section/main/div/div/header/section[4]/div/span/div/span')
		txt = bio_el.text.strip()
		if txt and txt != full_name:  # Evitar que sea el nombre
			biografia = txt
	except NoSuchElementException:
		pass
	
	if not biografia:
		try:
			# Estrategia 2: Relativo section[4]
			bio_el = driver.find_element(By.XPATH, '//section/main/div/div/header/section[4]//span')
			txt = bio_el.text.strip()
			if txt and txt != full_name:
				biografia = txt
		except NoSuchElementException:
			pass
	
	if not biografia:
		try:
			# Estrategia 3: Buscar span después del h1 (la bio suele estar justo debajo del nombre)
			header = driver.find_element(By.XPATH, '//section//header')
			# Intentar encontrar el span que esté después del h1 y que no sea el nombre
			bio_candidates = header.find_elements(By.XPATH, './/h1/following-sibling::div//span | .//section[4]//span')
			for candidate in bio_candidates:
				txt = candidate.text.strip()
				# Debe tener texto, no ser el nombre, y no ser solo números (contadores)
				if txt and txt != full_name and len(txt) > 5 and not txt.replace(',', '').replace('.', '').replace('k', '').replace('K', '').replace('M', '').replace('m', '').isdigit():
					biografia = txt
					break
		except NoSuchElementException:
			pass
	
	if not biografia:
		try:
			# Estrategia 4: Buscar todos los span y excluir nombre + números
			header = driver.find_element(By.XPATH, '//section//header')
			spans = header.find_elements(By.XPATH, './/span')
			for span in spans:
				txt = span.text.strip()
				# Filtro: no es el nombre, tiene más de 10 chars, no es solo números
				if txt and txt != full_name and len(txt) > 10 and not txt.replace(',', '').replace('.', '').isdigit():
					biografia = txt
					break
		except NoSuchElementException:
			pass

	# Fallback regex
	if not biografia:
		bio_raw = safe_text(r'"biography":"(.*?)"', source)
		biografia = decode_json_string(bio_raw)

	# Tipo de cuenta mediante XPath (badge "Empresa", "Creador de contenido", etc.)
	tipo_cuenta = None
	try:
		type_el = driver.find_element(By.XPATH, '//section//header//div[contains(text(), "Cuenta profesional") or contains(text(), "Empresa") or contains(text(), "Creador") or contains(text(), "Creator") or contains(text(), "Business")]')
		type_text = type_el.text.strip().upper()
		if "EMPRESA" in type_text or "BUSINESS" in type_text:
			tipo_cuenta = "BUSINESS"
		elif "CREADOR" in type_text or "CREATOR" in type_text:
			tipo_cuenta = "CREATOR"
		else:
			tipo_cuenta = "PROFESSIONAL"
	except NoSuchElementException:
		pass

	# Fallback regex
	if not tipo_cuenta:
		tipo_cuenta = parse_account_type(source)
	if not tipo_cuenta:
		tipo_cuenta = "PERSONAL"  # Asumir personal si no hay badge

	# Seguidores y seguidos mediante XPath
	seguidores = None
	seguidos = None
	try:
		# Instagram muestra los conteos en <span> dentro de <a href="/username/followers/"> y <a href="/username/following/">
		followers_el = driver.find_element(By.XPATH, f'//a[contains(@href, "/{username}/followers/")]//span//span | //a[contains(@href, "/followers/")]//span[contains(@class, "_ac2a") or contains(@class, "html-span")]')
		followers_text = followers_el.get_attribute("title") or followers_el.text.strip()
		seguidores = normalize_count(followers_text)
	except NoSuchElementException:
		pass

	try:
		following_el = driver.find_element(By.XPATH, f'//a[contains(@href, "/{username}/following/")]//span//span | //a[contains(@href, "/following/")]//span[contains(@class, "_ac2a") or contains(@class, "html-span")]')
		following_text = following_el.get_attribute("title") or following_el.text.strip()
		seguidos = normalize_count(following_text)
	except NoSuchElementException:
		pass

	# Fallback regex
	if seguidores is None or seguidos is None:
		followers_fallback, following_fallback = parse_counts(source)
		if seguidores is None:
			seguidores = followers_fallback
		if seguidos is None:
			seguidos = following_fallback

	return ProfileData(
		username=username,
		nombre=full_name,
		biografia=biografia,
		tipo_cuenta=tipo_cuenta,
		seguidores=seguidores,
		seguidos=seguidos,
		perfil_url=url,
	)


def main() -> None:
	driver = build_driver()
	try:
		login(driver, INSTA_USERNAME, INSTA_PASSWORD)
		open_following_modal(driver, TARGET_ACCOUNT)

		usernames = collect_following_usernames(driver)
		if MAX_PROFILES:
			usernames = usernames[:MAX_PROFILES]

		print(f" Scrapeando {len(usernames)} perfiles")
		results: List[ProfileData] = []
		for idx, user in enumerate(usernames, 1):
			print(f" ({idx}/{len(usernames)}) @{user}")
			try:
				data = scrape_profile(driver, user)
				results.append(data)
			except Exception as exc:  # noqa: BLE001
				print(f"  Error en @{user}: {exc}")
			human_sleep(2.0, 5.0, label="pausa entre perfiles")

		with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
			json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
		print(f" Guardado en {OUTPUT_JSON}")

	finally:
		driver.quit()


if __name__ == "__main__":
	main()
