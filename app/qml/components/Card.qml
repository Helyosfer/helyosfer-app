import QtQuick
import ".."

Rectangle {
    default property alias content: body.data
    property int padding: 20
    // For a panel that stands for one thing (an account, a goal): its frame
    // brightens under the pointer.
    property bool responsive: false

    color: Theme.panel
    radius: Theme.radius
    border.width: 1
    border.color: responsive && pointer.hovered ? Theme.line : Theme.lineSoft
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }
    HoverHandler { id: pointer; enabled: parent.responsive }
    implicitHeight: body.childrenRect.height + padding * 2

    Item {
        id: body
        anchors.fill: parent
        anchors.margins: parent.padding
    }
}
