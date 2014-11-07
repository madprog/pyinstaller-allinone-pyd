$ORIGINAL_PATH = (split-path $MyInvocation.MyCommand.Path)

function Invoke-NativeCommand {
  $command = $args[0];
  $arguments = $args[1..($args.Length)];
  write-host -foreground green "$command $arguments";
  & $command @arguments;
  if ($LastExitCode) {
    Write-Error "Exit code $LastExitCode while running $command $arguments";
    cd $ORIGINAL_PATH;
    exit 1;
  }
}

Invoke-NativeCommand C:\Python27\Scripts\pyinstaller.exe loader.spec;
Invoke-NativeCommand C:\Python27\Scripts\pyinstaller.exe my_module.spec;
cd dist;
Invoke-NativeCommand .\loader.exe;

cd $ORIGINAL_PATH;
