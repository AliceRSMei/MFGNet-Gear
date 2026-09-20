Attribute VB_Name = "saveply251"
' ******************************************************************************
' SOLIDWORKS macro for exporting configurations as PLY files.
' Personal/local paths and author metadata removed for publication.
' ******************************************************************************
Dim swApp As Object
Dim Part As Object
Dim boolstatus As Boolean
Dim longstatus As Long, longwarnings As Long

Sub main()

Set swApp = Application.SldWorks

Set Part = swApp.ActiveDoc
Dim COSMOSWORKSObj As Object
Dim CWAddinCallBackObj As Object
Set CWAddinCallBackObj = swApp.GetAddInObject("CosmosWorks.CosmosWorks")
Set COSMOSWORKSObj = CWAddinCallBackObj.COSMOSWORKS
configNames = Part.GetConfigurationNames()
For i = 0 To UBound(configNames) - 1
boolstatus = Part.Extension.SelectByID2(configNames(i), "CONFIGURATIONS", 0, 0, 0, False, 0, Nothing, 0)
Part.ClearSelection2 True
boolstatus = Part.Extension.SelectByID2(configNames(i), "CONFIGURATIONS", 0, 0, 0, False, 0, Nothing, 0)
boolstatus = Part.ShowConfiguration2(configNames(i))


' Save As
' Replace <OUTPUT_DIRECTORY> with the folder where PLY files should be saved.
' Replace <PART_FILE_NAME> with the name of the .SLDPRT file that contains the configurations.
' Example: if the part file is ExamplePart.SLDPRT, use "Default@ExamplePart.SLDPRT".
longstatus = Part.SaveAs3("<OUTPUT_DIRECTORY>\" + configNames(i) + ".PLY", 0, 2)
boolstatus = Part.Extension.SelectByID2("Default@<PART_FILE_NAME>.SLDPRT", "CONFIGURATIONS", 0, 0, 0, False, 0, Nothing, 0)
boolstatus = Part.ShowConfiguration2("Default")
boolstatus = Part.Extension.SelectByID2(configNames(i), "CONFIGURATIONS", 0, 0, 0, False, 0, Nothing, 0)
boolstatus = Part.Extension.SelectByID2(configNames(i), "CONFIGURATIONS", 0, 0, 0, False, 0, Nothing, 0)
Part.EditDelete
boolstatus = Part.DeleteConfiguration2(configNames(i))
Next i
End Sub
