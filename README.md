# homeCamera

Projet de camera de garage sur Raspberry Pi Zero 2W pour surveiller le passage
des chats, avec acces a distance et notifications photo.

Le projet peut aussi fonctionner directement sur un Mac mini avec une camera USB.

## Objectif

- Voir le flux camera a distance.
- Capturer des images lorsqu'un animal passe.
- Envoyer une photo sur Discord dans un premier temps.
- Garder une porte ouverte vers une vraie detection de chats plus tard.

## Mode Mac mini avec camera USB

Si la camera est branchee directement au Mac mini, le plus simple est d'utiliser
`ffmpeg` / `ffplay`.

Lister les cameras disponibles:

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

Dans la liste actuelle, la camera USB est:

```text
[1] LumenPnP Bottom
```

Faire une preview video:

```bash
./scripts/mac_usb_preview.sh
```

Forcer explicitement la camera USB par son nom:

```bash
./scripts/mac_usb_preview.sh -d "LumenPnP Bottom"
```

Capturer une image:

```bash
./scripts/mac_usb_capture.sh
```

Capturer une courte video:

```bash
./scripts/mac_usb_capture_video.sh --duration 5
```

Corriger une image trop claire:

```bash
./scripts/mac_usb_preview.sh --brightness -0.25 --contrast 1.15
./scripts/mac_usb_capture.sh --brightness -0.25 --contrast 1.15
```

Si c'est encore trop clair:

```bash
./scripts/mac_usb_capture.sh --brightness -0.40 --contrast 1.25 --gamma 0.85
```

Tester plusieurs niveaux de luminosite et mesurer l'image:

```bash
./scripts/mac_usb_brightness_bracket.sh
```

Cela cree un dossier `captures/brightness-test-*` avec les images et un fichier
`brightness_report.csv`. Chaque ligne contient le niveau `--brightness`, la
luminosite moyenne en pourcentage et le chemin de l'image.

Exemple plus resserre:

```bash
./scripts/mac_usb_brightness_bracket.sh --start -0.50 --step 0.05 -n 10
```

Ouvrir la derniere capture:

```bash
open "$(./scripts/list_captures.sh | head -1)"
```

Faire une rafale:

```bash
./scripts/mac_usb_burst.sh -n 5 -i 2
```

Surveiller le mouvement et capturer automatiquement:

```bash
./scripts/mac_usb_motion_watch.py
```

Verifier que le chemin de capture automatique fonctionne:

```bash
./scripts/mac_usb_motion_watch.py --force-capture
```

Afficher les scores de mouvement en direct:

```bash
./scripts/mac_usb_motion_watch.py --debug
```

Si le score est tres haut meme sans mouvement, garder la normalisation de
luminosite active et remonter `--pixel-delta`:

```bash
./scripts/mac_usb_motion_watch.py --debug --threshold 0.01 --pixel-delta 25 --consecutive 2
```

Reglages utiles:

```bash
./scripts/mac_usb_motion_watch.py --threshold 0.04 --cooldown 60
./scripts/mac_usb_motion_watch.py -r 30
./scripts/mac_usb_motion_watch.py --capture-size 1920x1080
./scripts/mac_usb_motion_watch.py -d "LumenPnP Bottom" --capture-rate 30
./scripts/mac_usb_motion_watch.py --brightness -0.25 --contrast 1.15
./scripts/mac_usb_motion_watch.py --background-alpha 2
```

Le watcher libere la camera au moment de la capture, prend la photo, puis
relance la surveillance. Cela evite deux acces simultanes a la meme camera USB
sur macOS.

Envoyer aussi la photo sur Discord:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
./scripts/mac_usb_motion_watch.py --discord
```

Envoyer une courte video sur Discord a chaque mouvement:

```bash
./scripts/mac_usb_motion_watch.py \
  --discord \
  --capture-kind video \
  --video-duration 5 \
  --capture-size 1280x720 \
  --threshold 0.005 \
  --pixel-delta 40 \
  --consecutive 1 \
  --cooldown 30
```

Ajuster automatiquement la luminosite vers la cible choisie pendant le test:

```bash
./scripts/mac_usb_motion_watch.py \
  --discord \
  --capture-kind video \
  --video-duration 5 \
  --capture-size 1280x720 \
  --auto-brightness \
  --target-luma 31.4 \
  --brightness-check-interval 600
```

La cible `31.4` correspond a la capture `brightness=0.100` du test de
luminosite. Le watcher mesure la luminosite moyenne du flux et ajuste le
parametre logiciel `--brightness` pour les videos suivantes.

Tester immediatement l'envoi d'une video sans attendre un mouvement:

```bash
./scripts/mac_usb_motion_watch.py --discord --force-capture --capture-kind video --video-duration 5
```

## Demarrage automatique sur Mac

Le demarrage automatique utilise un LaunchAgent utilisateur. Avec FileVault
active, il demarre apres le premier deverrouillage de session, pas avant.

Creer le fichier `.env` local:

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Tester la commande qui sera lancee par le service:

```bash
./scripts/run_mac_usb_motion_watch.sh
```

Interrompre avec `Ctrl+C`, puis installer et lancer le LaunchAgent:

```bash
./scripts/install_macos_launch_agent.sh
```

Verifier son etat et lire les logs:

```bash
./scripts/status_macos_launch_agent.sh
```

Suivre les logs en direct:

```bash
tail -f logs/motion-watch.out.log logs/motion-watch.err.log
```

Arreter et supprimer le LaunchAgent:

```bash
./scripts/uninstall_macos_launch_agent.sh
```

Modifier les parametres du bot dans:

```text
scripts/run_mac_usb_motion_watch.sh
```

Par defaut, ce wrapper lance maintenant une video de 5 secondes en `1280x720` a
chaque detection de mouvement, avec luminosite automatique ciblee a `31.4 %`.

La detection se fait sur une image basse resolution en niveaux de gris, puis une
capture propre est faite uniquement quand le mouvement est confirme. C'est plus
leger et plus stable que de sauvegarder un flux video complet.

Changer de camera si besoin:

```bash
./scripts/mac_usb_preview.sh -d 0
./scripts/mac_usb_capture.sh -d "LumenPnP Bottom" -s 1920x1080
```

La camera `LumenPnP Bottom` accepte notamment `1280x720@30`, `1280x720@10`,
`1920x1080@30`, `1920x1080@25`, `1920x1080@20`, `1920x1080@15`,
`1920x1080@10` et `1920x1080@5`. Les scripts utilisent donc `30 fps` par
defaut.

L'erreur `Input/output error` apres la commande de liste des devices est normale:
`ffmpeg` a bien affiche la liste, puis echoue parce qu'aucune vraie source video
n'a ete demandee.

## Mode Raspberry Pi Zero 2W

## Materiel conseille

- Raspberry Pi Zero 2W.
- Carte microSD 32 Go ou plus, de bonne qualite.
- Alimentation stable 5 V / 2 A.
- Camera Raspberry Pi Camera Module 2, Camera Module 3, ou camera NoIR si le
  garage est sombre.
- Nappe camera compatible Zero.
- Eclairage IR si camera NoIR, ou petit eclairage LED faible si camera normale.
- Boitier ou support oriente vers la zone de gamelle.

Le Zero 2W est suffisant pour capturer des images, diffuser un flux leger et
faire une detection simple. Il est en revanche limite pour de la detection IA
continue en haute resolution.

## Architecture recommandee

```text
Camera CSI
   |
Raspberry Pi Zero 2W
   |
   +-- Flux local leger: rpicam / mjpeg / RTSP
   |
   +-- Detection mouvement: motion ou script Python
   |
   +-- Notification: webhook Discord
   |
   +-- Acces distant: Tailscale ou VPN
```

### Acces distant

La solution la plus simple et la plus sure est d'utiliser un VPN de type
Tailscale. Cela evite d'ouvrir un port de la box internet vers le Raspberry Pi.

Eviter autant que possible:

- redirection de port directe vers la camera ;
- interface admin exposee publiquement ;
- mot de passe par defaut ;
- flux non chiffre accessible depuis Internet.

## Logiciel de base

Installer Raspberry Pi OS Lite 64-bit si possible. Sur les versions recentes de
Raspberry Pi OS, la pile camera moderne utilise `rpicam-*` et non plus les
anciens outils `raspistill` / `raspivid`.

Commandes utiles sur le Raspberry Pi:

```bash
sudo apt update
sudo apt install -y rpicam-apps python3-picamera2 python3-venv
```

Tester la camera:

```bash
rpicam-hello --timeout 5000
rpicam-jpeg -o test.jpg
```

## Captures de test rapides

Une fois le depot copie sur le Raspberry Pi:

```bash
cd ~/homeCamera
./scripts/capture_test.sh
```

Par defaut, l'image est enregistree dans `captures/` avec un nom horodate:

```text
captures/test-YYYYmmdd-HHMMSS.jpg
```

Capturer vers un fichier precis:

```bash
./scripts/capture_test.sh -o captures/gamelle.jpg
```

Tester en meilleure resolution pour verifier le cadrage:

```bash
./scripts/capture_test.sh -w 1920 -h 1080 -t 2500
```

Faire une rafale de 5 photos espacees de 2 secondes:

```bash
./scripts/capture_burst.sh
```

Faire une rafale plus longue:

```bash
./scripts/capture_burst.sh -n 10 -i 1
```

Lister les dernieres captures:

```bash
./scripts/list_captures.sh
```

Recuperer une capture sur le Mac:

```bash
scp chalume@Chalume.local:/home/chalume/homeCamera/captures/gamelle.jpg ~/Desktop/gamelle.jpg
```

## Flux video pour regler la focale

Pour regler la focale, lancer un flux H.264 depuis le Raspberry Pi:

```bash
cd ~/homeCamera
./scripts/start_focus_stream.sh
```

Depuis le Mac, ouvrir VLC puis `File > Open Network` avec:

```text
tcp/h264://chalume.local:8888
```

Le flux reste actif jusqu'a `Ctrl+C` sur le Raspberry Pi.

Variante en 1080p si le Wi-Fi suit:

```bash
./scripts/start_focus_stream.sh -w 1920 -h 1080 -f 15
```

## Etape 1: flux camera simple

Pour commencer, privilegier un flux basse resolution afin de ne pas saturer le
Zero 2W.

Exemple de capture video:

```bash
rpicam-vid --width 1280 --height 720 --framerate 15 --codec h264 -o test.h264
```

Options possibles ensuite:

- `motion`: simple, robuste, detection de mouvement integree.
- `go2rtc` ou `mediamtx`: plus oriente RTSP/WebRTC, pratique pour integration
  domotique.
- script Python avec Picamera2: plus flexible pour capturer et notifier.

## Etape 2: detection de passage

Pour un garage et une gamelle, commencer par detection de mouvement:

- zone de detection limitee a l'endroit ou les chats passent ;
- seuil assez haut pour ignorer bruit video et changements de lumiere ;
- delai anti-spam entre deux notifications ;
- sauvegarde d'une photo par evenement.

La detection "chat specifique" peut venir ensuite avec un modele leger:

- MobileNet SSD / TensorFlow Lite ;
- YOLO nano exporte en TFLite ou NCNN ;
- detection ponctuelle sur image declenchee par mouvement, plutot que detection
  continue sur toutes les frames.

Sur Pi Zero 2W, le meilleur compromis est:

1. mouvement detecte ;
2. capture d'une image ;
3. inference IA sur cette image ;
4. notification seulement si `cat` est detecte.

## Etape 3: notification Discord

Discord est le plus simple: creer un webhook dans un salon, puis poster une
image via HTTP.

Variables a prevoir:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Exemple de logique:

```text
si mouvement detecte:
  capturer image
  attendre 1 a 2 secondes pour avoir le chat dans le cadre
  envoyer photo sur Discord
  attendre 30 a 120 secondes avant prochaine notification
```

## WhatsApp

WhatsApp est possible, mais moins direct. Il faut generalement passer par:

- WhatsApp Business Cloud API ;
- un numero configure pour l'API ;
- des templates ou contraintes de messagerie selon le type d'envoi.

Pour ce projet, Discord est recommande pour demarrer. WhatsApp peut etre ajoute
ensuite si le besoin est fort.

## Plan de realisation

1. Installer Raspberry Pi OS Lite et activer SSH.
2. Connecter le Pi au Wi-Fi du garage.
3. Installer et tester la camera avec `rpicam-jpeg`.
4. Installer Tailscale pour l'acces distant.
5. Mettre en place un flux local leger.
6. Ajouter detection de mouvement + capture photo.
7. Ajouter webhook Discord.
8. Ajouter detection IA de chat si les notifications de mouvement sont trop
   bruyantes.

## Points importants

- Prevoir une bonne lumiere ou une camera NoIR avec eclairage IR.
- Fixer le champ de vision sur la zone de nourriture, pas tout le garage.
- Limiter la resolution pour economiser CPU et reseau.
- Stocker peu d'images localement, ou purger automatiquement les anciennes.
- Ne pas exposer directement le Pi sur Internet.

## Prochaine implementation possible

Le depot peut ensuite contenir:

```text
homeCamera/
  README.md
  scripts/
    capture_burst.sh
    capture_test.sh
    list_captures.sh
    send_discord_photo.py
    start_focus_stream.sh
  systemd/
    home-camera.service
  config/
    motion.conf
```

La premiere version utile serait un script Python qui capture une photo et
l'envoie sur Discord, puis un service `systemd` qui tourne en permanence.
