using System.Globalization;
using System.Text.Json.Nodes;

namespace SnowRunnerEnhanced;

internal static class StatusView
{
    internal static List<TerminalUi.Line> Build(JsonObject status, bool french, int width = 74, TimeZoneInfo? timeZone = null)
    {
        string T(string fr, string en) => french ? fr : en;
        bool installed = status["installed"]?.GetValue<bool>() == true;
        var lines = new List<TerminalUi.Line>
        {
            new(T("ÉTAT D’ENHANCED", "VIEW STATUS"), TerminalUi.Accent),
            new(new string('─', 66), TerminalUi.Border),
            new(installed
                ? T("Enhanced installé", "Enhanced installed") + " · " + (status["installedVersion"]?.GetValue<string>() ?? T("Version inconnue", "Unknown version"))
                : T("Enhanced n’est pas installé.", "Enhanced is not installed.")),
            new("", Optional: true)
        };
        if (installed)
        {
            (string Name, string Config, string Key)[] features =
            {
                (T("Souris et volant simultanés", "Simultaneous Mouse & Wheel Input"), "wheelMouseEnabled", "wheel_mouse"),
                (T("Passer les logos de démarrage", "Skip Startup Logos"), "skipStartupLogosEnabled", "skip_startup_logos"),
                (T("Carte", "Map"), "mapEnabled", "map"),
                (T("Améliorations générales", "General Improvements"), "generalImprovementsEnabled", "general_improvements"),
                (T("Véhicule", "Vehicle"), "vehicleEnabled", "vehicle"),
                (T("Améliorations du volant", "Steering Wheel Improvements"), "steeringWheelImprovementsEnabled", "steering_wheel_improvements")
            };
            string configuredHeading = T("CONFIGURATION", "CONFIGURED"), launchHeading = T("DERNIER LANCEMENT", "LAST LAUNCH");
            bool compact = width < 66;
            if (!compact)
                lines.Add(new(T("AMÉLIORATION", "ENHANCEMENT").PadRight(35) + configuredHeading.PadRight(15) + launchHeading, TerminalUi.Muted));
            var runtime = status["lastRun"];
            var differences = new List<string>();
            bool hasError = false;
            foreach (var feature in features)
            {
                bool? enabled = status[feature.Config]?.GetValue<bool>();
                var recorded = runtime?["features"]?[feature.Key];
                string? state = recorded?["status"]?.GetValue<string>();
                var (label, color) = State(state, runtime != null, french);
                hasError |= color == TerminalUi.Error;
                string configured = enabled.HasValue ? enabled.Value ? T("Activé", "Enabled") : T("Désactivé", "Disabled") : T("Inconnu", "Unknown");
                string configuredColor = enabled == true ? TerminalUi.Foreground : TerminalUi.Muted;
                if (compact)
                {
                    lines.Add(new(feature.Name));
                    lines.Add(TerminalUi.Colored(new("  " + configuredHeading + "  ", TerminalUi.Muted), new(configured, configuredColor)));
                    lines.Add(TerminalUi.Colored(new("  " + launchHeading + "  ", TerminalUi.Muted), new(label, color)));
                    lines.Add(new("", Optional: true));
                }
                else
                    lines.Add(TerminalUi.Colored(new(feature.Name.PadRight(35)), new(configured.PadRight(15), configuredColor), new(label, color)));

                bool? wasEnabled = recorded?["enabled"]?.GetValue<bool>() ?? (state switch
                {
                    "disabled" => false,
                    "active" or "waiting" or "pending" or "armed" => true,
                    _ => (bool?)null
                });
                if (enabled.HasValue && wasEnabled.HasValue && enabled != wasEnabled) differences.Add(feature.Name);
            }
            lines.Add(new("", Optional: true));
            if (runtime != null)
            {
                string date = T("Date inconnue", "Unknown date");
                if (DateTimeOffset.TryParse(runtime["timeUtc"]?.GetValue<string>(), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var utc))
                    date = TimeZoneInfo.ConvertTime(utc, timeZone ?? TimeZoneInfo.Local).ToString(
                        french ? "d MMM yyyy, HH:mm" : "MMM d, yyyy, h:mm tt", CultureInfo.GetCultureInfo(french ? "fr-CA" : "en-US"));
                lines.Add(new(T("Dernier lancement enregistré · ", "Last recorded launch · ") + date + T(" (heure locale)", " (local time)"), TerminalUi.Muted));
            }
            else
                lines.Add(new(T("Aucun lancement enregistré. Lancez le jeu, puis revenez vérifier l’activation.",
                    "No recorded launch. Start the game, then return to check activation."), TerminalUi.Muted));
            if (differences.Count > 0)
            {
                lines.Add(new("", Optional: true));
                lines.Add(new(T("Choix modifiés depuis le dernier lancement : ", "Choices changed since the last launch: ") + string.Join(", ", differences) + ".", TerminalUi.Warning));
                lines.Add(new(T("Ces choix prendront effet au prochain lancement de SnowRunner.",
                    "These choices take effect when you next launch SnowRunner."), TerminalUi.Muted));
            }
            if (hasError)
                lines.Add(new(T("Une amélioration a rencontré une erreur. Consultez le diagnostic.",
                    "An enhancement encountered an error. Check the diagnostic."), TerminalUi.Error));
            if (status["configurationError"] != null)
                lines.Add(new(T("Configuration absente ou invalide. Consultez le diagnostic.",
                    "Missing or invalid configuration. Check the diagnostic."), TerminalUi.Error));
            if (status["files"] is JsonObject files)
                foreach (var entry in files)
                    if (entry.Value?.GetValue<string>() != "owned")
                        lines.Add(new(entry.Key + " · " + (entry.Value?.GetValue<string>() == "missing"
                            ? T("Fichier manquant", "Missing file") : T("Fichier modifié", "Modified file")), TerminalUi.Error));
        }
        if (status["conflicts"] is JsonArray conflicts && conflicts.Count > 0)
            lines.Add(new(T("Fichiers déjà présents : ", "Existing files: ") + string.Join(", ", conflicts.Select(x => x!.GetValue<string>())), TerminalUi.Warning));
        if (status["loaderSupported"]?.GetValue<bool>() == false)
            lines.Add(new(T("Problème de chargement : ", "Loader problem: ") + status["loaderReason"]?.GetValue<string>(), TerminalUi.Error));
        return lines;
    }

    internal static (string Label, string Color) State(string? state, bool hasRun, bool french)
    {
        if (!hasRun) return ("—", TerminalUi.Muted);
        return state switch
        {
            "active" => (french ? "Actif" : "Active", TerminalUi.Success),
            "disabled" => (french ? "Désactivé" : "Disabled", TerminalUi.Muted),
            "waiting" or "pending" or "armed" => (french ? "En attente" : "Waiting", TerminalUi.Warning),
            null or "unknown" => (french ? "Inconnu" : "Unknown", TerminalUi.Muted),
            _ => (french ? "Erreur" : "Error", TerminalUi.Error)
        };
    }
}
