using System.Diagnostics;
using System.Reflection.PortableExecutable;
using System.Runtime.InteropServices;
using System.Text;

namespace SnowRunnerEnhanced;

// Inspect the PE as data: never load or execute a player's DLL in the installer.
// Recognition is a compatibility heuristic, not authentication of the publisher.
internal sealed class AsiLoader(bool french)
{
    internal IOException Problem(string fr, string en) => new(french ? fr : en);

    internal string Recognize(string path)
    {
        try
        {
            using var stream = File.OpenRead(path);
            using var pe = new PEReader(stream);
            var header = pe.PEHeaders.PEHeader;
            if (pe.PEHeaders.CoffHeader.Machine == Machine.I386)
                throw Problem("Ce chargeur est en 32 bits. SnowRunner nécessite Ultimate ASI Loader en version 64 bits. Le fichier existant a été conservé.",
                    "This loader is 32-bit. SnowRunner requires the 64-bit version of Ultimate ASI Loader. The existing file was preserved.");
            if (pe.PEHeaders.CoffHeader.Machine != Machine.Amd64 || header?.Magic != PEMagic.PE32Plus ||
                (pe.PEHeaders.CoffHeader.Characteristics & Characteristics.Dll) == 0)
                throw new BadImageFormatException();

            var version = FileVersionInfo.GetVersionInfo(path);
            bool identity = version.CompanyName == "ThirteenAG" &&
                version.ProductName is "Ultimate-ASI-Loader" or "Ultimate-ASI-Loader-x64" &&
                version.FileDescription == "Ultimate ASI Loader";
            if (!identity || !HasLoaderExports(pe))
                throw Problem("Le fichier dinput8.dll existant n’est pas reconnu comme Ultimate ASI Loader x64. Il a été conservé pour préserver vos autres mods. Vérifiez de quel mod il provient avant d’installer le chargeur officiel x64.",
                    "The existing dinput8.dll is not recognized as Ultimate ASI Loader x64. It was preserved to protect your other mods. Check which mod supplied it before installing the official x64 loader.");
            return version.FileVersion ?? "";
        }
        catch (Exception error) when (error is BadImageFormatException or ArgumentOutOfRangeException or OverflowException or InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            throw Problem("Le fichier dinput8.dll n’est pas une DLL Windows x64 valide. Il a été conservé. Restaurez une copie valide d’Ultimate ASI Loader x64 avant de réessayer.",
                "The dinput8.dll file is not a valid Windows x64 DLL. It was preserved. Restore a valid copy of Ultimate ASI Loader x64 before trying again.");
        }
    }

    static byte[] Read(PEReader pe, int rva, int size)
    {
        if (rva <= 0 || size < 0) throw new BadImageFormatException();
        return pe.GetSectionData(rva).GetContent(0, size).ToArray();
    }

    static bool HasLoaderExports(PEReader pe)
    {
        var directory = pe.PEHeaders.PEHeader!.ExportTableDirectory;
        if (directory.RelativeVirtualAddress <= 0 || directory.Size < 40) return false;
        var table = Read(pe, directory.RelativeVirtualAddress, 40);
        int functions = BitConverter.ToInt32(table, 20), names = BitConverter.ToInt32(table, 24);
        if (functions <= 0 || functions > 16384 || names <= 0 || names > 16384) return false;
        var addresses = Read(pe, BitConverter.ToInt32(table, 28), checked(functions * 4));
        var pointers = Read(pe, BitConverter.ToInt32(table, 32), checked(names * 4));
        var ordinals = Read(pe, BitConverter.ToInt32(table, 36), checked(names * 2));
        var required = new HashSet<string>(StringComparer.Ordinal) { "IsUltimateASILoader", "DirectInput8Create" };
        for (int i = 0; i < names; i++)
        {
            int nameRva = BitConverter.ToInt32(pointers, i * 4);
            if (nameRva <= 0) throw new BadImageFormatException();
            var bytes = pe.GetSectionData(nameRva).GetContent().Take(256).ToArray();
            int end = Array.IndexOf(bytes, (byte)0);
            if (end < 0) throw new BadImageFormatException();
            string name = Encoding.ASCII.GetString(bytes, 0, end);
            if (!required.Contains(name)) continue;
            int ordinal = BitConverter.ToUInt16(ordinals, i * 2);
            if (ordinal >= functions) return false;
            int address = BitConverter.ToInt32(addresses, ordinal * 4);
            // A name alone (or a forwarded export) is not enough.
            if (address <= 0 || (address >= directory.RelativeVirtualAddress &&
                (long)address < (long)directory.RelativeVirtualAddress + directory.Size)) return false;
            if (!pe.PEHeaders.SectionHeaders.Any(s => address >= s.VirtualAddress &&
                (long)address < (long)s.VirtualAddress + s.SizeOfRawData &&
                (s.SectionCharacteristics & SectionCharacteristics.MemExecute) != 0)) return false;
            Read(pe, address, 1);
            required.Remove(name);
        }
        return required.Count == 0;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetPrivateProfileIntW", ExactSpelling = true)]
    static extern uint ProfileInt(string section, string key, int fallback, string path);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetPrivateProfileStringW", ExactSpelling = true)]
    static extern uint ProfileString(string section, string key, string fallback, StringBuilder value, uint size, string path);

    string? Setting(string path, string key)
    {
        const string missing = "\u0001";
        var value = new StringBuilder(65536);
        uint length = ProfileString("GlobalSets", key, missing, value, (uint)value.Capacity, path);
        if (length >= value.Capacity - 1)
            throw Problem("Un réglage du chargeur est trop long pour être lu : " + key + ". Vérifiez le fichier " + path,
                "A loader setting is too long to read: " + key + ". Check the file " + path);
        string text = value.ToString();
        return text == missing ? null : text;
    }

    internal void CheckConfiguration(string folder, bool supportsExtraPlugins)
    {
        // Same per-key precedence and Win32 INI semantics as UAL 8.5 / 10.0.2.
        string[] files = ["dinput8.ini", "global.ini", @"scripts\global.ini", @"plugins\global.ini", @"update\global.ini"];
        var settings = new Dictionary<string, int> { ["LoadPlugins"] = 1, ["LoadFromScriptsOnly"] = 0, ["DontLoadFromDllMain"] = 1 };
        var origins = new Dictionary<string, string>();
        string extraPlugins = "";
        foreach (string file in files)
        {
            string path = Path.Combine(folder, file);
            Installation.CheckPath(path);
            if (Directory.Exists(path))
                throw Problem("Un dossier occupe l’emplacement du fichier de configuration du chargeur : " + file + ". Déplacez ce dossier avant de réessayer.",
                    "A directory occupies the loader configuration file location: " + file + ". Move that directory before trying again.");
            if (!File.Exists(path)) continue;
            // Verify readability instead of silently treating an unreadable INI as absent.
            using var readable = File.OpenRead(path);
            foreach (string key in settings.Keys.ToArray())
            {
                int value = unchecked((int)ProfileInt("GlobalSets", key, settings[key], path));
                if (Setting(path, key) != null) origins[key] = file;
                settings[key] = value;
            }
            extraPlugins = Setting(path, "LoadExtraPlugins") ?? extraPlugins;
        }
        void Require(string key, bool enabled, string fr, string en)
        {
            if ((settings[key] != 0) == enabled) return;
            string fix = origins.GetValueOrDefault(key, "dinput8.ini") + ": [GlobalSets] " + key + "=" + (enabled ? "1" : "0");
            throw Problem(fr + " Réglage à corriger : " + fix + ". Vos fichiers ont été conservés.",
                en + " Setting to change: " + fix + ". Your files were preserved.");
        }
        Require("LoadPlugins", true, "Le chargement des mods est désactivé dans votre chargeur.", "Your loader has mod loading disabled.");
        bool explicitPlugin = supportsExtraPlugins && extraPlugins.Split('|').Any(entry =>
        {
            try { return Path.GetFullPath(entry.Trim(), folder).Equals(Path.Combine(folder, "SnowRunnerEnhanced.asi"), StringComparison.OrdinalIgnoreCase); }
            catch (Exception error) when (error is ArgumentException or NotSupportedException or PathTooLongException) { return false; }
        });
        if (!explicitPlugin)
            Require("LoadFromScriptsOnly", false, "Votre chargeur ignore le dossier où SnowRunner Enhanced est installé.", "Your loader skips the folder where SnowRunner Enhanced is installed.");
        Require("DontLoadFromDllMain", true, "Votre chargeur initialise les mods trop tôt pour SnowRunner Enhanced.", "Your loader initializes mods too early for SnowRunner Enhanced.");
        string chained = Path.Combine(folder, "dinput8Hooked.dll");
        Installation.CheckPath(chained);
        if (File.Exists(chained) || Directory.Exists(chained))
            throw Problem("Un proxy DirectInput supplémentaire (dinput8Hooked.dll) nécessite une vérification manuelle de la configuration de vos mods avant l’installation. Vos fichiers ont été conservés.",
                "An additional DirectInput proxy (dinput8Hooked.dll) requires a manual check of your mod configuration before installation. Your files were preserved.");
    }
}
