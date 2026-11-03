using System;
using System.IO;
using System.Text;
using System.Threading;
using Windows.Media;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Devices.Enumeration;
using Windows.Foundation;

// Experimental observation only. Raw media names are not mapped to joystick keys.
public sealed class InputProbe : IDisposable
{
    private readonly MediaPlayer player;
    private readonly SystemMediaTransportControls controls;
    private readonly MediaPlaybackItem item;
    private readonly MediaSource source;
    private readonly ManualResetEvent stop;
    private static readonly object outputLock = new object();
    private static long sequence;

    private static string Quote(string value)
    {
        var text = new StringBuilder("\"");
        foreach (char ch in value ?? "")
        {
            if (ch == '"' || ch == '\\') { text.Append('\\'); text.Append(ch); }
            else if (ch < 32) text.Append("\\u" + ((int)ch).ToString("x4"));
            else text.Append(ch);
        }
        return text.Append('"').ToString();
    }

    private static void Emit(string kind, string value)
    {
        lock (outputLock)
        {
            Console.WriteLine("{\"source\":\"smtc\",\"type\":" + Quote(kind) +
                ",\"value\":" + Quote(value) + ",\"sequence\":" + (++sequence) +
                ",\"utc\":" + Quote(DateTime.UtcNow.ToString("o")) + "}");
            Console.Out.Flush();
        }
    }

    public InputProbe(string endpointHint, string wavePath, ManualResetEvent stopEvent)
    {
        stop = stopEvent;
        Emit("stage", "endpoint_lookup");
        var operation = DeviceInformation.FindAllAsync(DeviceClass.AudioRender);
        using (var ready = new ManualResetEvent(false))
        {
            operation.Completed = (result, status) => {
                try { ready.Set(); } catch (ObjectDisposedException) { }
            };
            if (!ready.WaitOne(8000)) { operation.Cancel(); throw new TimeoutException("Endpoint lookup timed out"); }
            if (operation.Status != AsyncStatus.Completed) throw new Exception("Endpoint lookup failed");
        }
        DeviceInformation selected = null;
        int matches = 0;
        foreach (var device in operation.GetResults())
        {
            if (device.Id.IndexOf(endpointHint, StringComparison.OrdinalIgnoreCase) >= 0 ||
                device.Name.IndexOf(endpointHint, StringComparison.OrdinalIgnoreCase) >= 0)
            { selected = device; matches++; }
        }
        if (matches != 1) throw new Exception("Endpoint hint must match exactly one audio output");
        Emit("stage", "endpoint_matched");
        player = new MediaPlayer();
        player.AudioDevice = selected;
        player.IsMuted = true;
        player.IsLoopingEnabled = true;
        player.CommandManager.IsEnabled = false;
        Emit("stage", "player_created");
        controls = player.SystemMediaTransportControls;
        controls.IsEnabled = true;
        controls.IsPlayEnabled = controls.IsPauseEnabled = true;
        controls.IsNextEnabled = controls.IsPreviousEnabled = true;
        controls.IsStopEnabled = controls.IsRecordEnabled = true;
        controls.IsFastForwardEnabled = controls.IsRewindEnabled = true;
        controls.IsChannelUpEnabled = controls.IsChannelDownEnabled = true;
        controls.ButtonPressed += (sender, args) => {
            Emit("button", args.Button.ToString());
            if (args.Button == SystemMediaTransportControlsButton.Play)
            { player.Play(); controls.PlaybackStatus = MediaPlaybackStatus.Playing; }
            else if (args.Button == SystemMediaTransportControlsButton.Pause)
            { player.Pause(); controls.PlaybackStatus = MediaPlaybackStatus.Paused; }
        };
        controls.PropertyChanged += (sender, args) => Emit("property", args.Property.ToString());
        controls.PlaybackPositionChangeRequested += (sender, args) => Emit("seek", args.RequestedPlaybackPosition.ToString());
        player.VolumeChanged += (sender, args) => Emit("player_volume", player.Volume.ToString(System.Globalization.CultureInfo.InvariantCulture));
        player.PlaybackSession.PlaybackStateChanged += (sender, args) => Emit("playback", sender.PlaybackState.ToString());
        player.MediaFailed += (sender, args) => { Emit("error", args.ErrorMessage); stop.Set(); };
        player.MediaOpened += (sender, args) => Emit("ready", "all_media_buttons_enabled");
        controls.DisplayUpdater.Type = MediaPlaybackType.Music;
        controls.DisplayUpdater.MusicProperties.Title = "Pixeldeck input probe";
        controls.DisplayUpdater.MusicProperties.Artist = "Local diagnostics";
        controls.DisplayUpdater.Update();
        controls.PlaybackStatus = MediaPlaybackStatus.Playing;
        Emit("stage", "controls_configured");
        Emit("stage", "uri_creating");
        var uri = new Uri(Path.GetFullPath(wavePath));
        Emit("stage", "media_source_creating");
        source = MediaSource.CreateFromUri(uri);
        Emit("stage", "playback_item_creating");
        item = new MediaPlaybackItem(source);
        Emit("stage", "source_assigning");
        player.Source = item;
        Emit("stage", "source_assigned");
        player.Play();
        Emit("stage", "play_requested");
    }

    public void Dispose()
    {
        if (controls != null) controls.IsEnabled = false;
        if (player != null) player.Dispose();
        GC.KeepAlive(item);
        GC.KeepAlive(source);
    }

    [MTAThread]
    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        if (args.Length == 1 && args[0] == "--self-test-json")
        { Emit("button", "ChannelUp"); Emit("button", "Stop"); return 0; }
        int seconds;
        if (args.Length != 3 || !int.TryParse(args[2], out seconds) || seconds < 1 || seconds > 600)
        { Console.Error.WriteLine("Usage: InputProbe.exe ENDPOINT_HINT SILENCE_WAV SECONDS(1..600)"); return 2; }
        using (var done = new ManualResetEvent(false))
        using (var deadline = new Timer(_ => {
            try { done.Set(); } catch (ObjectDisposedException) { }
        }, null, seconds*1000, Timeout.Infinite))
        {
            var input = new Thread(() => {
                try {
                    string line;
                    while ((line = Console.ReadLine()) != null) {
                        if (line == "stop") { done.Set(); return; }
                        if (line.StartsWith("mark ", StringComparison.Ordinal)) Emit("marker", line.Substring(5, Math.Min(40, line.Length-5)));
                    }
                } catch { done.Set(); }
            });
            input.IsBackground = true; input.Start();
            try {
                using (var probe = new InputProbe(args[0], args[1], done)) done.WaitOne();
                Emit("closed", "released"); return 0;
            } catch (Exception ex) { Emit("error", ex.Message); return 1; }
        }
    }
}
