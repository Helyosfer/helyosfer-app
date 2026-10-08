import QtQuick
import ".."

Rectangle {
    default property alias content: body.data
    property int padding: 20

    color: Theme.panel
    radius: Theme.radius
    border.width: 1
    border.color: Theme.lineSoft
    implicitHeight: body.childrenRect.height + padding * 2

    Item {
        id: body
        anchors.fill: parent
        anchors.margins: parent.padding
    }
}
